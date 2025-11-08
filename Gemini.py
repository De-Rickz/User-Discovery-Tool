import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

gen_AI_Key = os.getenv("GOOGLE_API_KEY")
# 1. Configure the client (finds key in environment)
client = genai.Client(api_key=gen_AI_Key)

# 2. Define our data and instructions
scraped_context = "QuantumLeap Capital has $113M AUM... They posted a blog 'Redirecting Focus' in August 2025."
instruction_template = """
Prompt Objective: Determine if [COMPANY NAME]...
...
5. Suggested personalised outreach snippet...
"""

# 3. Create the final prompt
final_prompt = f"""Here is the context I found:
{scraped_context}
---
Now, using only the context above, perform the following task:
{instruction_template}
"""

# 4. Call the AI
ai_response = client.models.generate_content(
    model='gemini-pro',
    contents=final_prompt
)