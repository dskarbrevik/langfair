"""
.. _response_generator_demo:

===============================================================
``ResponseGenerator`` Class
===============================================================

"""
# %%
#
# Import necessary libraries for the notebook.

# Run if python-dotenv not installed
# import sys
# !{sys.executable} -m pip install python-dotenv

import json
import os
import time

import openai
import pandas as pd
from dotenv import load_dotenv

from langfair.generator import ResponseGenerator

# User to populate .env file with API credentials
repo_path = "/".join(os.getcwd().split("/")[:-2])
load_dotenv(os.path.join(repo_path, ".env"))

API_KEY = os.getenv("API_KEY")
API_BASE = os.getenv("API_BASE")
API_TYPE = os.getenv("API_TYPE")
API_VERSION = os.getenv("API_VERSION")
MODEL_VERSION = os.getenv("MODEL_VERSION")
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME")

# %%
# Read in prompts from which responses will be generated.


# THIS IS AN EXAMPLE SET OF PROMPTS
resource_path = os.path.join(repo_path, "data/RealToxicityPrompts.jsonl")
with open(resource_path, "r") as file:
    # Read each line in the file
    challenging = []
    prompts = []
    for line in file:
        # Parse the JSON object from each line
        challenging.append(json.loads(line)["challenging"])
        prompts.append(json.loads(line)["prompt"]["text"])
prompts = [prompts[i] for i in range(len(prompts)) if not challenging[i]][0:1000]

# %%
# ``ResponseGenerator()`` - Class for generating data for evaluation from provided set of prompts (class)
#
# Class parameters:
#
# - ``langchain_llm`` (**langchain llm (Runnable), default=None**) A langchain llm object to get passed to LLMChain `llm` argument.
# - ``suppressed_exceptions`` (**tuple, default=None**) Specifies which exceptions to handle as 'Unable to get response' rather than raising the exception
# - ``max_calls_per_min`` (**Deprecated as of 0.2.0**) Use LangChain's InMemoryRateLimiter instead.
#
# Below we use LangFair's ``ResponseGenerator`` class to generate LLM responses. To instantiate the ``ResponseGenerator`` class, pass a LangChain LLM object as an argument. Note that although this notebook uses ``AzureChatOpenAI``, this can be replaced with a LangChain LLM of your choice.

# # Run if langchain-openai not installed
# import sys
# !{sys.executable} -m pip install langchain-openai

# Example with AzureChatOpenAI. REPLACE WITH YOUR LLM OF CHOICE.
from langchain_openai import AzureChatOpenAI

llm = AzureChatOpenAI(
    deployment_name=DEPLOYMENT_NAME,
    openai_api_key=API_KEY,
    azure_endpoint=API_BASE,
    openai_api_type=API_TYPE,
    openai_api_version=API_VERSION,
    temperature=1,  # User to set temperature
)


# Create langfair ResponseGenerator object
rg = ResponseGenerator(
    langchain_llm=llm,
    suppressed_exceptions=(
        openai.BadRequestError,
        ValueError,
    ),  # this suppresses content filtering errors
)

# %%
# **Estimate token costs before generation**
#
# ``estimate_token_cost()`` - Estimates the token cost for a given list of prompts and (optionally) example responses. This method is only compatible with GPT models.
#
#  Method Parameters:
#
#   - ``prompts`` - (**list of strings**) A list of prompts.
#   - ``example_responses`` - (**list of strings, optional**) A list of example responses. If provided, the function will estimate the response tokens based on these examples.
#   - ``model_name`` - (**str, optional**) The name of the OpenAI model to use for token counting.
#   - ``response_sample_size`` - (**int, default=30**) The number of responses to generate for cost estimation if `response_example_list` is not provided.
#   - ``system_prompt`` - (**str, default="You are a helpful assistant."**) The system prompt to use.
#   - ``count`` - (**int, default=25**) The number of generations per prompt used when estimating cost.
#
# Returns:
# - A dictionary containing the estimated token costs, including prompt token cost, completion token cost, and total token cost. (**dictionary**)


for model_name in ["gpt-3.5-turbo-16k-0613", "gpt-4-32k-0613"]:
    estimated_cost = await rg.estimate_token_cost(
        tiktoken_model_name=model_name, prompts=prompts, count=1
    )
    print(
        f"Estimated cost for {model_name}: $",
        round(estimated_cost["Estimated Total Token Cost (USD)"], 2),
    )

# %%
# .. note::
#   Note that using GPT-4 is considerably more expensive than GPT-3.5
#
# Evaluating Response Time: Asynchronous Generation with ``ResponseGenerator`` vs Synchronous Generation with ``openai.chat.completions.create``
# *********************************************************************************************************************************************************************************************
#
# Generate responses asynchronously with ``ResponseGenerator``
#
# ``generate_responses()`` -  Generates evaluation dataset from a provided set of prompts. For each prompt, ``self.count`` responses are generated.
# Method Parameters:
#
# - ``prompts`` - (**list of strings**) A list of prompts
# - ``system_prompt`` - (**str or None, default="You are a helpful assistant."**) Specifies the system prompt used when generating LLM responses.
# - ``count`` - (**int, default=25**) Specifies number of responses to generate for each prompt.
#
# Returns:
# A dictionary with two keys: ``data`` and ``metadata``.
# - ``data`` (**dict**) A dictionary containing the prompts and responses.
# - ``metadata`` (**dict**) A dictionary containing metadata about the generation process, including non-completion rate, temperature, and count.

# Generate 1 response per prompt for 200 prompts
start = time.time()
async_responses = await rg.generate_responses(prompts=prompts[0:200], count=1)
stop = time.time()
print(f"Time elapsed for asynchronous generation: {stop - start}")

pd.DataFrame(async_responses["data"])

async_responses["metadata"]


# Generate responses synchronously for comparison


def openai_api_call(
    prompt, system_prompt="You are a helpful assistant.", model="exai-gpt-35-turbo-16k"
):
    try:
        completion = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        return completion.choices[0].message.content
    except openai.BadRequestError:
        return "Unable to get response"


openai.api_key = API_KEY
openai.azure_endpoint = API_BASE
openai.model_version = MODEL_VERSION
openai.api_version = API_VERSION
openai.api_type = API_TYPE

start = time.time()
sync_responses = [openai_api_call(prompt) for prompt in prompts[0:200]]
stop = time.time()
print(f"Time elapsed for synchronous generation: {stop - start}")

# %%
# Note that asynchronous generation with `ResponseGenerator` is significantly faster than synchonous generation.
#
# Handling ``RateLimitError`` with ``ResponseGenerator``
#
# Passing too many requests asynchronously will trigger a ``RateLimitError``. For our '`exai-gpt-35-turbo-16k`' deployment, 1000 prompts at 25 generations per prompt with async exceeds the rate limit.

responses = await rg.generate_responses(prompts=prompts)

# %%
# To handle this error, we can use ``max_calls_per_min`` to limit the number of requests per minute.

from langchain_core.rate_limiters import InMemoryRateLimiter

rate_limiter = InMemoryRateLimiter(
    requests_per_second=5,
    check_every_n_seconds=5,
    max_bucket_size=500,
)

llm = AzureChatOpenAI(
    deployment_name=DEPLOYMENT_NAME,
    openai_api_key=API_KEY,
    azure_endpoint=API_BASE,
    openai_api_type=API_TYPE,
    openai_api_version=API_VERSION,
    temperature=1,  # User to set temperature
    rate_limiter=rate_limiter,
)

rg_limited = ResponseGenerator(langchain_llm=llm)

responses = await rg_limited.generate_responses(prompts=prompts)

pd.DataFrame(responses["data"])
