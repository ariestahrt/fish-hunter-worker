import json
from utils.html_utils import *
from utils.css_utils import *

def get_dataset_features(dataset_path):
    # clean dataset
    # cleaning HTML
    html_text = open(dataset_path+"/index.html", "r").read()
    html_clean = remove_hidden_element(html_text=html_text, html_root=dataset_path+"/")
    
    # Save clean html to clean.html
    with open(dataset_path+"/clean.html", "w", encoding="utf-8") as f:
        f.write(html_clean)
    
    # Get only-used css
    css_dict = get_css_from_html(html_clean, html_root=dataset_path+"/")
    
    # Save clean css to assets/__clean__.css
    convert_cssdict_to_cssfile(css_dict, save_to=dataset_path+"/assets/__clean__.css")
    
    # Rebuild html with only-used css
    html = lxml.html.parse(StringIO(html_clean))
    for element in html.getroot().iter():
        if element.attrib.get("rel") != None:
            if element.tag == "link" and "stylesheet" in element.attrib["rel"]:
                # remove the element
                element.getparent().remove(element)
    
    # Add new link to clean css
    head = html.find(".//head")
    link = lxml.html.Element("link", rel="stylesheet", href="assets/__clean__.css")
    head.append(link)

    # Save to clean.html
    with open(dataset_path+"/clean.html", "w", encoding="utf-8") as f:
        f.write(lxml.html.tostring(html, encoding="unicode"))

    css_propval = extract_css_propval_from_file(dataset_path+"/assets/__clean__.css")
    # Save css_propval to css.json
    with open(dataset_path+"/css.json", "w", encoding="utf-8") as f:
        json.dump(css_propval, f, indent=4, sort_keys=True)

    # GET TEXT FEATURES
    html_text = open(dataset_path+"/clean.html", "r").read()
    feature_text = get_rendered_text(html_text)

    # GET HTML STRUCTURE FEATURES
    feature_html = json.dumps(get_html_structure(html_text))

    # GET CSS FEATURES
    feature_css = json.dumps(css_propval)

    return feature_text, feature_html, feature_css