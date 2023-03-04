FROM python:3.8

WORKDIR /fish-hunter-worker

COPY . /fish-hunter-worker

# Adding trusting keys to apt for repositories
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -

# Adding Google Chrome to the repositories
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

# update
RUN apt-get -y update

# install 7zip, nano, screen, sudo, google-chrome-stable
RUN apt-get install -y p7zip-full nano screen sudo google-chrome-stable cron

# Installing Unzip
RUN apt-get install -yqq unzip

# Download the Chrome Driver
RUN wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/`\
curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE\
`/chromedriver_linux64.zip

# Unzip the Chrome Driver into /usr/local/bin directory
RUN unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/

# Set display port as an environment variable
ENV DISPLAY=:99

# install dependencies
RUN python3 -m pip install -r requirements.txt

CMD ["/bin/bash"]