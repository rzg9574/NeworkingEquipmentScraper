# syntax=docker/dockerfile:1
FROM python:3.9-slim

RUN mkdir /app
COPY . /app
WORKDIR /app
ADD requirements.txt /app
#COPY . /app

RUN apt-get update && apt-get install -y wget \
    unzip \
    curl \
    gnupg \
    libgconf-2-4 \
    default-jdk \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get update && apt-get install -y google-chrome-stable

RUN wget -O /tmp/chromedriver-win64.zip https://storage.googleapis.com/chrome-for-testing-public/128.0.6613.137/win64/chromedriver-win64.zip
RUN unzip /tmp/chromedriver-win64.zip -d /usr/local/bin/



ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt install python3-pip -y
RUN pip3 install fake_headers
RUN pip3 install PyPDF2
RUN pip3 install wget
RUN pip3 install -r requirements.txt


CMD ["python3",  "./app.py" ]
