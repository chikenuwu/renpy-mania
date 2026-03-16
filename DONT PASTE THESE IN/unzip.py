import zipfile

#was for unzipping osz file
with zipfile.ZipFile("yourfile.osz", "r") as z:
    z.extractall("name_of_unzipped_folder")
