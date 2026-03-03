################################# Stage 1: Base environment setup ######################################
FROM oraclelinux:8 AS base

RUN yum -y install unzip oraclelinux-developer-release-el8 && \
    yum -y install openssh-clients python36-oci-cli && \
    yum clean all

WORKDIR /tmp

################################# Stage 2: ZDM environment setup and local kit ######################################
FROM base AS zdm-setup

ARG ZDM_USER
ARG ZDM_GROUP
ARG HOME_DIR
ARG HOSTNAME
ARG ZDM_HOME
ARG ZDM_BASE
ARG ZDM_INSTALL_LOG
ARG ZEUS_DATA
ARG ZEUS_BASE
ARG PATH

ENV HOME_DIR=$HOME_DIR \
    ZDM_HOME=$ZDM_HOME \
    ZDM_BASE=$ZDM_BASE \
    ZDM_INSTALL_LOG=$ZDM_INSTALL_LOG \
    ZEUS_DATA=$ZEUS_DATA \
    ZEUS_BASE=$ZEUS_BASE \
    PATH=$PATH

USER root
RUN yum -y install libaio libnsl ncurses-compat-libs expect glibc-devel hostname numactl openssl python3 sudo openssh-clients xz xz-libs lsof && \
    yum clean all

RUN mkdir -p $ZDM_HOME $ZDM_BASE $ZEUS_DATA $ZEUS_BASE $ZEUS_BASE/log $ZDM_INSTALL_LOG && \
    ls -la /u01

RUN groupadd -g 1000 $ZDM_GROUP && \
    useradd -u 1000 -m -d $HOME_DIR -g $ZDM_GROUP $ZDM_USER

RUN chown -R $ZDM_USER:$ZDM_GROUP \
    $HOME_DIR \
    "$(dirname "$ZDM_HOME")" \
    $ZDM_HOME \
    $ZDM_BASE \
    $ZEUS_DATA \
    $ZEUS_BASE \
    $ZEUS_BASE/log \
    $ZDM_INSTALL_LOG

RUN mkdir -p $HOME_DIR/.ssh && \
    ssh-keygen -m PEM -t rsa -b 4096 -N '' -f $HOME_DIR/.ssh/id_rsa && \
    chmod 600 $HOME_DIR/.ssh/id_rsa $HOME_DIR/.ssh/id_rsa.pub && \
    chown -R $ZDM_USER:$ZDM_GROUP $HOME_DIR/.ssh

COPY --chown=$ZDM_USER:$ZDM_GROUP .local_zdm /tmp/local_zdm

USER $ZDM_USER
WORKDIR $HOME_DIR

# Require local kit only
RUN if [ ! -f /tmp/local_zdm/zdm.zip ]; then echo 'Local kit not found at /tmp/local_zdm/zdm.zip'; exit 1; fi; \
    cp /tmp/local_zdm/zdm.zip $HOME_DIR/zdm.zip

RUN unzip $HOME_DIR/zdm.zip -d $HOME_DIR/unzipped

################################## Stage 3: Final ZDM environment ######################################
FROM zdm-setup AS final

# Declare the build arguments
ARG ZDM_USER
ARG ZDM_GROUP

# Switch to root user for file operations
USER root
# Copy application code and startup scripts into the container
COPY zdm-microservices $HOME_DIR/zdm-microservices
COPY start_zdm.sh start_zeus.sh restart_microservice.sh restart_streamlit.sh $HOME_DIR/

# Change ownership and executable bits
RUN chown -R $ZDM_USER:$ZDM_GROUP \
    $HOME_DIR/zdm-microservices \
    $HOME_DIR/start_zdm.sh \
    $HOME_DIR/start_zeus.sh \
    $HOME_DIR/restart_microservice.sh \
    $HOME_DIR/restart_streamlit.sh && \
    find $HOME_DIR -maxdepth 1 -type f -name \"*.sh\" -exec chmod +x {} \\; && \
    find $HOME_DIR/zdm-microservices -maxdepth 1 -type f -name \"*.sh\" -exec chmod +x {} \\; || true

# Switch to $ZDM_USER before running pip3 install
USER $ZDM_USER

# Set the PYTHONUSERBASE to point to $ZDM_USER's home directory
ENV PYTHONUSERBASE=$HOME_DIR/.local

# Install Python packages in the user's local directory
RUN pip3 install --user -r $HOME_DIR/zdm-microservices/requirements.txt
RUN pip3 install --user --upgrade typing_extensions && \
    ls -la /u01

CMD ["/bin/bash", "-c", "/home/zdmuser/start_zdm.sh && exec /home/zdmuser/start_zeus.sh"]

# Add a health check to confirm the script has finished running
HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=20 CMD test -f ${ZEUS_BASE}/log/.zeus_finished || exit 1
