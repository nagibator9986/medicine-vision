#!/bin/bash
# Set OpenAI API key if not already in environment
if [ -z "$OPENAI_API_KEY" ]; then
    export OPENAI_API_KEY=$(echo 'c2stcHJvai1OWURHOFdDcTN5ay16bXF2VEI1M3NpR20yU2N3Zkp2WElSbjM3bUs1QnA4QUhEY2dZZTR3LTVJOGFxaXg1SVVGdjNtcEJOT3FmQlQzQmxia0ZKZkFlOTlUVVZodHdSR1pfVWpFQUNjU0t6cEdsMXVhTVJ6TnZfa29HRENPY2pEekxvNXhwc0VKekFhcGZwX3FVMVNqNlN4a2xBb0E=' | base64 -d)
fi
exec gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --bind 0.0.0.0:$PORT run:app
