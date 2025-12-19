import os
import json

config_dir = "data"
config_file = "config.json"
default_opacity = 50
config_path = os.path.join(config_dir, config_file)

def load_config():
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            opacity = int(config.get('opacity_percent', default_opacity))
            opacity = max(0, min(50, opacity))
            return opacity
    except:
        return default_opacity

def save_config(_current_opacity):
    config = {'opacity_percent': _current_opacity}

    try:
        os.makedirs(config_dir, exist_ok=True)
    except:
        return
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
    except:
        pass
