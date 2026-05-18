################################# Stage 1: Base environment setup ######################################
FROM oraclelinux:8 AS base

RUN yum -y install unzip oraclelinux-developer-release-el8 && \
    yum -y install curl openssh-clients python3.11 python3.11-pip nodejs npm && \
    yum clean all

WORKDIR /tmp

################################# Stage 2: ZDM environment setup ######################################
FROM base AS zdm-setup

ARG ZDM_USER
ARG ZDM_GROUP
ARG HOME_DIR
ARG ZDM_HOME
ARG ZDM_BASE
ARG ZDM_INSTALL_LOG
ARG ZEUS_DATA
ARG ZEUS_BASE

ENV HOME_DIR=$HOME_DIR \
    ZDM_HOME=$ZDM_HOME \
    ZDM_BASE=$ZDM_BASE \
    ZDM_INSTALL_LOG=$ZDM_INSTALL_LOG \
    ZEUS_DATA=$ZEUS_DATA \
    ZEUS_BASE=$ZEUS_BASE

ENV PATH="${HOME_DIR}/.local/bin:${HOME_DIR}:${ZDM_HOME}/bin:${PATH}"

USER root

RUN yum -y install \
    libaio \
    libnsl \
    ncurses-compat-libs \
    expect \
    glibc-devel \
    hostname \
    numactl \
    openssl \
    sudo \
    openssh-clients \
    xz \
    xz-libs \
    lsof \
    gcc \
    gcc-c++ \
    make \
    && yum clean all

RUN mkdir -p "$ZDM_HOME" "$ZDM_BASE" "$ZEUS_DATA" "$ZEUS_BASE" "$ZEUS_BASE/log" "$ZDM_INSTALL_LOG" && \
    ls -la /u01

RUN groupadd -g 1000 "$ZDM_GROUP" && \
    useradd -u 1000 -m -d "$HOME_DIR" -g "$ZDM_GROUP" "$ZDM_USER"

RUN chown -R "$ZDM_USER:$ZDM_GROUP" \
    "$HOME_DIR" \
    "$(dirname "$ZDM_HOME")" \
    "$ZDM_HOME" \
    "$ZDM_BASE" \
    "$ZEUS_DATA" \
    "$ZEUS_BASE" \
    "$ZEUS_BASE/log" \
    "$ZDM_INSTALL_LOG"

RUN mkdir -p "$HOME_DIR/.ssh" && \
    ssh-keygen -m PEM -t rsa -b 4096 -N '' -f "$HOME_DIR/.ssh/id_rsa" && \
    chmod 600 "$HOME_DIR/.ssh/id_rsa" "$HOME_DIR/.ssh/id_rsa.pub" && \
    chown -R "$ZDM_USER:$ZDM_GROUP" "$HOME_DIR/.ssh"

USER $ZDM_USER
WORKDIR $HOME_DIR

# Persist bash command history
RUN mkdir -p "$ZEUS_DATA/.shell_history" && \
    touch "$ZEUS_DATA/.shell_history/.bash_history" && \
    ln -sf "$ZEUS_DATA/.shell_history/.bash_history" "$HOME_DIR/.bash_history"

RUN echo 'export HISTFILE=$HOME/.bash_history' >> "$HOME_DIR/.bashrc" && \
    echo 'export HISTSIZE=10000' >> "$HOME_DIR/.bashrc" && \
    echo 'export HISTFILESIZE=20000' >> "$HOME_DIR/.bashrc" && \
    echo 'shopt -s histappend' >> "$HOME_DIR/.bashrc" && \
    echo 'export PROMPT_COMMAND="history -a; history -n"' >> "$HOME_DIR/.bashrc"

################################## Stage 3: Final ZEUS environment ######################################
FROM zdm-setup AS final

ARG ZDM_USER
ARG ZDM_GROUP
ARG HOME_DIR

USER root

# Copy application code and container runtime scripts into the container
COPY zdm-microservices "$HOME_DIR/zdm-microservices"
COPY container-scripts/ "$HOME_DIR/"

# Change ownership and executable bits
RUN chown -R "$ZDM_USER:$ZDM_GROUP" "$HOME_DIR" && \
    find "$HOME_DIR" -maxdepth 1 -type f -name "*.sh" -exec chmod +x {} \; && \
    find "$HOME_DIR/zdm-microservices" -maxdepth 1 -type f -name "*.sh" -exec chmod +x {} \;

USER $ZDM_USER

ENV PYTHONUSERBASE=$HOME_DIR/.local

# Install Python packages in the user's local directory
RUN python3.11 -m pip install --user --upgrade pip setuptools wheel
RUN python3.11 -m pip install --user -r "$HOME_DIR/zdm-microservices/requirements.txt"
RUN python3.11 -m pip install --user --upgrade typing_extensions && \
    ls -la /u01

CMD ["/bin/bash", "-c", "/home/zdmuser/start_zdm.sh && exec /home/zdmuser/start_zeus.sh"]

HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=20 CMD [ -f "${ZEUS_BASE}/log/.zeus_finished" ] && curl --cacert "${ZEUS_BASE}/certs/zeus.crt" -skf "https://127.0.0.1:${ZEUS_PORT:-8001}/" || exit 1
