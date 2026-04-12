# fsatlas Docker image
# Builds on FreeSurfer 8.x base image and adds fsatlas Python package.
#
# Build:
#   docker build -t fsatlas .
#
# Run (license via CLI flag — recommended for containers):
#   docker run --rm \
#       -v /path/to/SUBJECTS_DIR:/subjects \
#       -v /path/to/license.txt:/license.txt:ro \
#       -e SUBJECTS_DIR=/subjects \
#       fsatlas --freesurfer-license-file /license.txt \
#               extract --atlas schaefer100-7 -o /subjects/fsatlas_output
#
# Run (license via FS_LICENSE env var):
#   docker run --rm \
#       -v /path/to/SUBJECTS_DIR:/subjects \
#       -v /path/to/license.txt:/license.txt:ro \
#       -e SUBJECTS_DIR=/subjects \
#       -e FS_LICENSE=/license.txt \
#       fsatlas extract --atlas schaefer100-7 -o /subjects/fsatlas_output

FROM freesurfer/freesurfer:8.0.0

# Install ANTs from a CentOS 7 release build (GLIBC 2.17+), which is
# forward-compatible with the AlmaLinux/CentOS base used by FreeSurfer 8.
# The antsx/ants:v2.6.5 image is Ubuntu 22.04-based (GLIBC 2.35+) and
# cannot run on the older C runtime shipped with freesurfer:8.0.0.
# ANTs 2.4.4 is the last release with a centos7-gcc build (GLIBC 2.17+),
# which is forward-compatible with Rocky Linux 8's GLIBC 2.28.
# The 2.5.x/2.6.x releases only ship Ubuntu 20.04/22.04 builds (GLIBC 2.31+),
# which cannot run on the Rocky Linux 8 base used by freesurfer:8.0.0.
ARG ANTS_VERSION=2.6.5
RUN dnf install -y unzip && dnf clean all \
    && curl -fsSL \
        "https://github.com/ANTsX/ANTs/releases/download/v${ANTS_VERSION}/ants-${ANTS_VERSION}-centos7-X64-gcc.zip" \
        -o /tmp/ants.zip \
    && unzip /tmp/ants.zip -d /tmp/ants_src \
    && mv /tmp/ants_src/ants-${ANTS_VERSION} /opt/ants \
    && rm -rf /tmp/ants.zip /tmp/ants_src
ENV ANTSPATH=/opt/ants/bin
ENV PATH="${ANTSPATH}:${PATH}"
RUN antsRegistration --version

# Install Python 3.11 and venv using whichever package manager is present
RUN if command -v apt-get >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends \
            python3.11 python3.11-pip python3.11-venv \
        && rm -rf /var/lib/apt/lists/*; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf install -y python3.11 python3.11-pip && dnf clean all; \
    elif command -v yum >/dev/null 2>&1; then \
        yum install -y python3.11 python3.11-pip && yum clean all; \
    else \
        echo "ERROR: no supported package manager found" >&2 && exit 1; \
    fi

# Create isolated venv to avoid system package conflicts
RUN python3.11 -m venv /opt/fsatlas-venv
ENV PATH="/opt/fsatlas-venv/bin:$PATH"

# Install fsatlas
WORKDIR /opt/fsatlas
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Populate the BIDS-atlas directory at build time so all atlases ship with
# the image. FreeSurfer is available here, so built-in LUTs are generated too.
ENV FSATLAS_ATLAS_DIR=/opt/fsatlas/atlases
RUN python /opt/fsatlas/scripts/build_bids_atlases.py \
        --output-dir /opt/fsatlas/atlases \
        --freesurfer-home "${FREESURFER_HOME:-/usr/local/freesurfer}"

ENTRYPOINT ["fsatlas"]
CMD ["--help"]
