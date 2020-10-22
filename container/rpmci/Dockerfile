#
# RPMci - Containerized RPMci Deployment
#
# This containerizes the `rpmci` project bundled with all its dependencies. We
# use the official `python` images from the docker library.
#
# The default entrypoint is `python -m rpmci`. This can be overriden by the
# caller, and it is explicitly supported to run the other `rpmci` modules.
#
# Build Arguments:
#
#   * RPMCI_HOST="docker.io/library/python:alpine"
#       This specifies the host image to use. It must provide a compatible
#       python implementation, as well as `pip`.
#

# Image arguments must be imported before `FROM`.
ARG             RPMCI_HOST="docker.io/library/python:alpine"

# Prepare our host environment.
FROM            "${RPMCI_HOST}" AS host

# Create our state directory and use it as anchor. Then create and switch into
# our src directory, which we use as temporary storage for all sources during
# the install.
WORKDIR         "/var/lib/rpmci"
WORKDIR         "./src"

# Import the full source directory from the import environment. Run it through
# pip to prepare our python environment and install the project.
COPY            "." "rpmci"
RUN             pip install "./rpmci/"

# Leave and delete our temporary install directory.
WORKDIR         ".."
RUN             rm -rf "./src"

# Prepare the runtime entrypoint and empty working directory.
WORKDIR         "./workdir"
ENTRYPOINT      ["python", "-m", "rpmci"]
