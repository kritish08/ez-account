from openai import OpenAI

endpoint = "https://ezaccounts-res.openai.azure.com/openai/v1/"
deployment_name = "gpt-5.2"
api_key = "8rQB9wWJPkFTsEtZoFSpTJqSlyeRJMSRUcMBluNbtq6iZD5Fhf2SJQQJ99CBACHYHv6XJ3w3AAAAACOGqikK"

client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": "What is the capital of France?",
        }
    ],
    temperature=0.7,
)

print(completion.choices[0].message)