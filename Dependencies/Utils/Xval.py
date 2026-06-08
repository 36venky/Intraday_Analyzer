def Xval(price):
    if price < 80:
        return 0.6
    elif 200 <= price < 600:
        return 0.6
    elif price >= 2000:
        return 0.6
    else:
        return 0.6