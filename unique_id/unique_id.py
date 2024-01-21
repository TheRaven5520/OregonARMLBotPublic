import os

def unique_id():
    _id = None
    with open(f"{os.path.dirname(__file__)}/unique_id.txt", "r") as file:
        _id = int(file.read())
    with open(f"{os.path.dirname(__file__)}/unique_id.txt", "w") as file:
        file.write(str(_id+1))
    return _id
