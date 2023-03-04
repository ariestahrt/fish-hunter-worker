from bs4 import BeautifulSoup
from utils.css_utils import get_css_from_html,convert_cssdict_to_cssfile,get_notdisplayed_style,convert_csstext_to_cssdict
import json
import re

def read_file(filename):
    text = ""
    with open(filename, "r", encoding="utf-8") as f: text += f.read()
    return text

# Return cleanest HTML File
def remove_hidden_element(html_text, html_root):
    soup = BeautifulSoup(html_text, 'html.parser')
    # Remove by html tag
    for element in soup.find_all(True):
        try: element.get('')
        except: continue

        if element.get('style'):
            inline_css = ".temp_inline" + "{" + element.get('style') + "}"
            css_dict_inline = {}
            convert_csstext_to_cssdict(inline_css, css_dict_inline, html_text=html_text, validate_css=False)
            useless_selector = get_notdisplayed_style(css_dict_inline)
            if len(useless_selector) > 0:
                print("Removing element", element.name)
                element.decompose()
                continue
        
        if element.get('width') != None and element.get('height') != None:
            width_val = float(re.findall('\d*\.?\d+',element.get('width'))[0]) if len(re.findall('\d*\.?\d+',element.get('width'))) > 0 else 9999
            height_val = float(re.findall('\d*\.?\d+',element.get('height'))[0]) if len(re.findall('\d*\.?\d+',element.get('height'))) > 0 else 9999
            wmin = 0.0 ; hmin = 0.0

            if "px" in element.get('width'): wmin = 1.0
            if "px" in element.get('height'): hmin = 1.0

            if width_val <= wmin and height_val <= hmin:
                element.decompose()

    # Remove by useless selector
    css_dict = get_css_from_html(html_text=html_text, html_root=html_root)

    useless_selector = get_notdisplayed_style(css_dict)
    for selector in useless_selector:
        print("Removing", selector)
        try:
            elements = soup.select(selector)
            for element in elements:
                element.decompose()
        except Exception as ex: None

    return soup.prettify()

# Get HTML structure
def get_html_structure(html):
    soup = BeautifulSoup(html, 'html.parser')
    res = []
    for element in soup.find_all(True):
        res.append(element.name)
    return res

# Get rendered text
def get_rendered_text(html):
    soup = BeautifulSoup(html, "html.parser")
    html_text = soup.get_text()

    # Cleaning the text
    while "\n\n" in html_text:
        html_text=html_text.replace("\n\n", "\n")

    while "\t" in html_text:
        html_text=html_text.replace("\t", " ")

    while "  " in html_text:
        html_text=html_text.replace("  ", " ")

    return html_text