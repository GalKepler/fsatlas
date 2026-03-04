# fsatlas Docker image
# Builds on FreeSurfer 8.x base image and adds fsatlas Python package.
#
# Usage:
#   docker build -t fsatlas .
#   docker run --rm -v /path/to/SUBJECTS_DIR:/subjects \
#       -e SUBJECTS_DIR=/subjects \
#       fsatlas extract --atlas schaefer100-7 -o /subjects/fsatlas_output
#
# NOTE: You must have a valid FreeSurfer license file.
# Mount it as: -v /path/to/license.txt:/opt/freesurfer/license.txt

FROM freesurfer/freesurfer:8.0.0

# Install Python 3.12 and pip (FS 8 ships with Python but may lack pip)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Create venv to avoid system package conflicts
RUN python3 -m venv /opt/fsatlas-venv
ENV PATH="/opt/fsatlas-venv/bin:$PATH"

# Install fsatlas
WORKDIR /opt/fsatlas
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Default: show help
ENTRYPOINT ["fsatlas"]
CMD ["--help"]
