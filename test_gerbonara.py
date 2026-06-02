import gerbonara
print(dir(gerbonara))

try:
    print(dir(gerbonara.cam))
except Exception as e:
    pass

try:
    print(dir(gerbonara.rs274x))
except Exception as e:
    pass
