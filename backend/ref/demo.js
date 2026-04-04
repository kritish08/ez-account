import OpenAI from "openai";

const endpoint = "https://ezaccounts-res.openai.azure.com/openai/v1/";
const deploymentName = "gpt-5.2";
const apiKey = "8rQB9wWJPkFTsEtZoFSpTJqSlyeRJMSRUcMBluNbtq6iZD5Fhf2SJQQJ99CBACHYHv6XJ3w3AAAAACOGqikK";

const openai = new OpenAI({
    baseURL: endpoint,
    apiKey: apiKey
});

async function main() {
    const completion = await openai.chat.completions.create({
        messages: [{ role: "developer", content: "You are a helpful assistant." }],
        model: deploymentName,
        store: true,
    });

    console.log(completion.choices[0]);
}

main();