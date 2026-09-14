import json
import urllib.request
import xml.etree.ElementTree as ET
from flask import Flask, render_template

app = Flask(__name__)

def fetch_rss_matches():
    url = "https://static.cricinfo.com/rss/livescores.xml"
    matches = {'live': [], 'upcoming': [], 'finished': []}
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ''
                description = item.find('description').text if item.find('description') is not None else ''
                
                # Parsing team scores and status from title/description
                parts = title.split('v')
                t1 = parts[0].strip() if len(parts) > 0 else 'Team A'
                t2 = parts[1].strip() if len(parts) > 1 else 'Team B'
                
                match_info = {
                    'title': title,
                    't1': t1,
                    't2': t2,
                    'status': description if description else 'Match status updating...',
                    'venue': 'International / Domestic Venue'
                }
                
                # Simple categorization logic
                title_lower = title.lower()
                desc_lower = description.lower()
                
                if 'won' in title_lower or 'won' in desc_lower or 'drawn' in title_lower:
                    matches['finished'].append(match_info)
                elif 'match over' in desc_lower or 'result' in desc_lower:
                    matches['finished'].append(match_info)
                elif 'match starts' in desc_lower or 'opt' in desc_lower or 'yet to' in desc_lower:
                    matches['upcoming'].append(match_info)
                else:
                    matches['live'].append(match_info)
                    
    except Exception as e:
        print(f"RSS Fetch Error: {e}")
        
    return matches

@app.route('/')
def home():
    matches = fetch_rss_matches()
    return render_template('index.html', matches=matches)

if __name__ == '__main__':
    app.run(debug=True)
