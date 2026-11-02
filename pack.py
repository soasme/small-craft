"""Write assets/textures.py, a module holding the texture atlas and the sky
as bytes, so spyc bundles the images as it bundles code. It runs on the
engine itself: ../../spy pack.py > assets/textures.py"""
print('"""textures/texture.png and textures/sky.png, written by pack.py; do not edit."""')
for name, path in (("TEXTURE_PNG", "textures/texture.png"), ("SKY_PNG", "textures/sky.png")):
    print(f"{name} = {open(path, 'rb').read()!r}")
