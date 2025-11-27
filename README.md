A fast, serverless search API built on top of a slow, paginated upstream data source.
Designed to meet the assignment requirement: return results in < 100 ms while not hitting the upstream API on every request.

## Features
•	Public HTTP API /search
•	Fast in-memory search (no external calls during requests)
•	Daily data refresh using EventBridge cron
•	Python Lambda backend with Pydantic validation
•	Clean pagination (page, page_size)
•	Fully serverless (AWS Lambda + API Gateway)
•	Deployable & publicly accessible

## Tech Stack
•	Python (latest stable)
•	AWS Lambda
•	AWS API Gateway (HTTP API)
•	AWS EventBridge (Cron Schedule)
•	Pydantic v1
•	Requests (to fetch slow upstream API once per refresh)

## API Usage

GET /search?query=jet&page=1&page_size=5

Response example

{
"query": "jet",
"page": 1,
"page_size": 5,
"total": 1,
"items": [
{
"id": "1",
"user_id": "u1",
"user_name": "Alice",
"timestamp": "2025-05-05T10:00:00Z",
"message": "Book a private jet to Paris."
}
]
}

## Example Search Request (Postman)

Below is an example of the `/search` endpoint working with query parameters:

![Postman Example](postman-example.png)


## Architecture Diagram

![Message Search Architecture](https://lucid.app/publicSegments/view/49b9b830-892d-4a06-aad7-ee6b2abdd5db/image.png)


## Deployment Steps

* Create Python venev
    python3 -m venv .venv
    source .venv/bin/activate
* Install dependencies
  pip install "pydantic==1.10.15" requests
* Build Lambda package
  rm -rf build lambda.zip
  mkdir build
  cp -r .venv/lib/python3*/site-packages/* build/
  cp -r lambda_src/message_search build/message_search
  cd build
  zip -r ../lambda.zip .
  cd ..
* Upload to AWS Lambda
* API Gateway Setup
* EventBridge Setup

## Design notes

### Goals and Constraints

The upstream API is slow.
The assignment requires API to return results under 100 ms.
The service must be publicly accessible.

_Because of this the key idea is to "decouple" fetching data from source
and serving search queries._

### Option A: Chosen approach : Serverless (Lambda + EventBridge)

Lambda function exposes 'Get/search' via API gateway
A daily eventbridge cron rule calls the same lambda but with a different event
{"source": "cron.refresh"}
1. In refresh mode, the lambda:
Calls the slow upstream API once (with a large limit).
Rebuilds an in-memory list of Message objects validating using pydantic.

2. In search mode, the lambda :
Uses the in-memory list and filters it.
Returns a paginated response in well under 100 ms.(except for lambda cold starts)

The Lambda loads messages.json on cold start, creating an in-memory dataset stored in a global variable (DATA).
AWS reuses the same execution environment for multiple invocations, so this in-memory dataset is also reused—making searches extremely fast.
A daily EventBridge cron trigger invokes the function in refresh mode, pulling fresh data from the slow Source API and updating the DATA variable.
Each Lambda environment maintains its own copy of DATA, so freshness is “best effort” and not strongly consistent across all concurrent execution environments.

Why I chose this approach:
Minimal infrastructure (one Lambda + API Gateway + EventBridge rule).


### Option B: 2 Lambdas, S3, API Gateway, EventBridge : 

A separate “loader” Lambda periodically calls the upstream API and writes the full dataset to an S3 object (`messages.json`).
- The search Lambda:
    - Reads `messages.json` from S3 on cold start.
    - Keeps the parsed data in memory for subsequent invocations.
- EventBridge would trigger the loader Lambda on a schedule.

Pros:

- Decouples the refresh logic from the search logic.
- S3 gives a persistent snapshot of the data.

Cons:

- Slightly more infrastructure (two Lambdas + S3).
- Extra S3 GET on cold start adds a bit of latency.

I chose to keep everything inside one Lambda for simplicity.


### Option C: DynamoDB-Backed Search : 
Another option is to:

- Load upstream data into a DynamoDB table (via a loader lambda).
- Expose a search API that queries DynamoDB.

Pros:

- Handles much larger datasets than what fits comfortably in memory.
- DynamoDB reads are low latency (typically single-digit milliseconds).

Cons:

- More complex data modeling (secondary indexes, partition keys).
- More AWS components and cost vs your simple in-memory design.
- Still adds an extra network call (Lambda → DynamoDB) on every request.

For this assignment’s scale and simplicity, DynamoDB felt like overkill compared to an in-memory list.


### Summary

I considered several ways to build the search engine:

- **Direct pass-through** to the upstream API → too slow.
- **S3-backed snapshots** → reasonable, but extra moving parts.
- **DynamoDB / database backed** search → scalable, but overkill here.

I ultimately chose a **serverless in-memory cache with a scheduled refresh**, which gives:

- Very low latency for search requests.
- A simple architecture that still looks like a real production pattern.
- A clear separation between “slow refresh” and “fast query” paths.