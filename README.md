# ondrive_dl
An interactive CLI wrapper for OneDrive

# Description

An interactive tool that leverages the OneDrive SDK to interact with OneDrive and perform common operations (list, upload, download files, etc.). 

# Usage

```
python3 onedrive_dl.py
usage: onedrive_dl.py [-h] [-a ACCESSTOKEN] [-o OUTPUTDIR]

Description of your program

options:
  -h, --help            show this help message and exit
  -a ACCESSTOKEN, --accesstoken ACCESSTOKEN
  -o OUTPUTDIR, --outputdir OUTPUTDIR
                        Directory to put files
```



# About tokens

This application expects an access token that has the `Microsoft Office` audience. Such a token can be created using the amazing tool `tokenman` (<https://github.com/secureworks/TokenMan>) with the following commandline. 

```
python3 tokenman.py swap -r <REFRESH_TOKEN> -c d3590ed6-52b3-4102-aeff-aad2292ab01c --resource "https://graph.microsoft.com"
```
*Note:* it is expected that a refresh token has been acquired here. If you have valid user credentials, such tokens can be acquired using various tools such as tokenman, or roadtx.

# Installation

```sh
pip install onedrive-sharepoint-python-sdk
pip install PyInquirer
```

*Note:* if you get an error similar to:

```python
Traceback (most recent call last):
  File "/home/kali/tools/onedrive_dl.py", line 13, in <module>
    from PyInquirer import prompt
  File "/home/kali/.local/lib/python3.11/site-packages/PyInquirer/__init__.py", line 6, in <module>
    from prompt_toolkit.token import Token
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/__init__.py", line 16, in <module>
    from .interface import CommandLineInterface
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/interface.py", line 19, in <module>
    from .application import Application, AbortAction
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/application.py", line 8, in <module>
    from .key_binding.bindings.basic import load_basic_bindings
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/key_binding/bindings/basic.py", line 9, in <module>
    from prompt_toolkit.renderer import HeightIsUnknownError
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/renderer.py", line 11, in <module>
    from prompt_toolkit.styles import Style
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/styles/__init__.py", line 8, in <module>
    from .from_dict import *
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/styles/from_dict.py", line 9, in <module>
    from collections import Mapping
ImportError: cannot import name 'Mapping' from 'collections' (/usr/lib/python3.11/collections/__init__.py)
```

Modify the line in the file `prompt_toolkit/styles/from_dict.py` referenced in the error (e.g. see below) FROM:

```python
  File "/home/kali/.local/lib/python3.11/site-packages/prompt_toolkit/styles/from_dict.py", line 9, in <module>
    from collections import Mapping
```

TO:

```python
    from collections.abc import Mapping
```