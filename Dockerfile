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

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Copy the pre-built BIDS atlas directory so containers work without internet
COPY bids_atlases/ /opt/fsatlas-atlases/
ENV FSATLAS_ATLASES_DIR=/opt/fsatlas-atlases

ENTRYPOINT ["fsatlas"]
CMD ["--help"]
