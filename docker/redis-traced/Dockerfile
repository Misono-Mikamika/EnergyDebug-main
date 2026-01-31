ARG BASE=ubuntu:22.04

FROM ${BASE} as build

RUN apt-get update \
    && apt-get install -y build-essential libelf-dev libdw-dev libunwind-dev

# 使用本地uftrace-master目录
COPY uftrace-master /uftrace
RUN cd /uftrace \
    && misc/install-deps.sh -y \
    && ./configure \
    && make \
    && make install

RUN apt-get update && apt-get install -y wget make build-essential

# 使用本地redis-7.0.12目录
COPY redis-7.0.12 /redis-stable
RUN cd /redis-stable \
    && make \
    && make install

EXPOSE 6379

WORKDIR /traces

COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]