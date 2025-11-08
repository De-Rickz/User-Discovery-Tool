# Discovery Tool
import requests

from bs4 import BeautifulSoup

# 1. Fetch Page

url = requests.get('https://example.com')

response = requests.get(url)

# 2. Parse URL

soup = BeautifulSoup(response.text, 'html.parser')

# 3. Find all the <h2> tags with the class "blog-post-title"
all_titles = soup.find_all('h2', class_ = 'blog-post-title')

# 4. Loop through the list and print the text of each title

for title in all_titles:
    print(title.text)
