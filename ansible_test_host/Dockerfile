FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y openssh-server netcat openssh-client python3 && apt-get clean

RUN mkdir /var/run/sshd

# Create .ssh directory for root and set permissions
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Copy the public key from the 'keys' folder to the authorized_keys of root
COPY keys/id_rsa.pub /root/.ssh/authorized_keys

# Set appropriate permissions on authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys

# Allow root login with password (preferably use SSH keys)
RUN echo 'root:rootpassword' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# Disable PAM (Pluggable Authentication Module)
RUN sed -i 's@session    required     pam_loginuid.so@session    optional     pam_loginuid.so@g' /etc/pam.d/sshd

RUN mkdir -p /tmp/.ansible/tmp && chmod -R 777 /tmp/.ansible

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D", "-e"]