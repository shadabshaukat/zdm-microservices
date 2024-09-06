################################# Stage 1: Base environment setup ######################################
FROM oraclelinux:8 AS base

# Install necessary packages for OCI CLI
RUN yum -y install unzip oraclelinux-developer-release-el8 && \
    yum -y install python36-oci-cli && \
    yum -y install openssh-clients && \
    yum clean all

# Set a default working directory
WORKDIR /tmp

################################# Stage 2: ZDM environment setup and file download ######################################
FROM base AS zdm-setup

# Declare the build arguments
ARG ZDM_USER
ARG ZDM_GROUP
ARG HOME_DIR
ARG ARTIFACT_ID
ARG HOSTNAME
ARG ZDM_HOME
ARG ZDM_BASE
ARG ZEUS_LOG
ARG PATH

# Set ARGs as ENV variables to make them available in the container environment
ENV HOME_DIR=$HOME_DIR \
    ZDM_HOME=$ZDM_HOME \
    ZDM_BASE=$ZDM_BASE \
    ZEUS_LOG=$ZEUS_LOG \
    PATH=$PATH

# Install additional packages for ZDM
USER root
RUN yum -y install libaio libnsl ncurses-compat-libs expect glibc-devel hostname numactl openssl python3 sudo openssh-clients && \
    yum clean all

# Create directories
RUN mkdir -p $ZDM_HOME $ZDM_BASE $ZEUS_LOG && \
    ls -la /u01

# Create a group and user for ZDM
RUN groupadd -g 1000 $ZDM_GROUP && \
    useradd -u 1000 -m -d $HOME_DIR -g $ZDM_GROUP $ZDM_USER

# Change with appropriate ownership
RUN chown -R $ZDM_USER:$ZDM_GROUP $HOME_DIR $ZDM_HOME $ZDM_BASE $ZEUS_LOG

# Create the SSH directory and generate SSH key without prompt
RUN mkdir -p $HOME_DIR/.ssh && \
    ssh-keygen -m PEM -t rsa -b 4096 -N '' -f $HOME_DIR/.ssh/id_rsa && \
    chmod 600 $HOME_DIR/.ssh/id_rsa $HOME_DIR/.ssh/id_rsa.pub

COPY --chown=$ZDM_USER:$ZDM_GROUP .oci $HOME_DIR/.oci

# Switch to $ZDM_USER
USER $ZDM_USER
WORKDIR $HOME_DIR

# Change permission of OCI config file
RUN oci setup repair-file-permissions --file $HOME_DIR/.oci/config

# Download the file from OCI Artifact Registry
RUN oci artifacts generic artifact download --artifact-id ${ARTIFACT_ID} --file zdm.zip

# Unzip the downloaded file
RUN unzip zdm.zip -d $HOME_DIR/unzipped

################################## Stage 3: Final ZDM environment ######################################
FROM zdm-setup AS final

# Declare the build arguments
ARG ZDM_USER
ARG ZDM_GROUP

# Switch to root user for file operations
USER root
# Copy the zdm-microservices directory into the container with the desired ownership
COPY zdm-microservices $HOME_DIR/zdm-microservices

# Change ownership of the directory and its files
RUN chown -R $ZDM_USER:$ZDM_GROUP $HOME_DIR/zdm-microservices

# Switch to $ZDM_USER before running pip3 install
USER $ZDM_USER

# Set the PYTHONUSERBASE to point to $ZDM_USER's home directory
ENV PYTHONUSERBASE=$HOME_DIR/.local

# Install Python packages in the user's local directory
RUN pip3 install --user -r $HOME_DIR/zdm-microservices/requirements.txt
RUN pip3 install --user --upgrade typing_extensions && \
    ls -la /u01

CMD ["/bin/bash", "-c", "/home/zdmuser/zdm-microservices/zeus.sh && tail -f /dev/null"]

# Add a health check to confirm the script has finished running
HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=20 CMD test -f $ZEUS_LOG/.zeus_finished || exit 1
