#!/bin/bash
rq worker signals --url $REDIS_URL &
uvicorn app:app --host 0.0.0.0 --port 10000
