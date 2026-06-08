def gat_angle(price:float) -> float:
    if price <= 5:
        return 5
    elif price <= 10:
        return 5 + (price - 5) * (7.5 - 5) / (10 - 5)
    elif price <= 20:
        return 7.5 + (price - 10) * (10 - 7.5) / (20 - 10)
    elif price <= 30:
        return 10 + (price - 20) * (15 - 10) / (30 - 20)
    elif price <= 40:
        return 15 + (price - 30) * (17.5 - 15) / (40 - 30)
    elif price <= 50:
        return 17.5 + (price - 40) * (20 - 17.5) / (50 - 40)
    elif price <= 75:
        return 20 + (price - 50) * (22.5 - 20) / (75 - 50)
    elif price <= 100:
        return 22.5 + (price - 75) * (25 - 22.5) / (100 - 75)
    elif price <= 125:
        return 25 + (price - 100) * (27.5 - 25) / (125 - 100)
    elif price <= 150:
        return 27.5 + (price - 125) * (30 - 27.5) / (150 - 125)
    elif price <= 175:
        return 30 + (price - 150) * (32.5 - 30) / (175 - 150)
    elif price <= 200:
        return 32.5 + (price - 175) * (35 - 32.5) / (200 - 175)
    elif price <= 225:
        return 35 + (price - 200) * (37.5 - 35) / (225 - 200)
    elif price <= 250:
        return 37.5 + (price - 225) * (40 - 37.5) / (250 - 225)
    elif price <= 300:
        return 40 + (price - 250) * (50 - 40) / (300 - 250)
    elif price <= 350:
        return 50 + (price - 300) * (52.5 - 50) / (350 - 300)
    elif price <= 400:
        return 52.5 + (price - 350) * (55 - 52.5) / (400 - 350)
    elif price <= 450:
        return 55 + (price - 400) * (57.5 - 55) / (450 - 400)
    elif price <= 500:
        return 57.5 + (price - 450) * (60 - 57.5) / (500 - 450)
    elif price <= 550:
        return 60 + (price - 500) * (62.5 - 60) / (550 - 500)
    elif price <= 600:
        return 62.5 + (price - 550) * (65 - 62.5) / (600 - 550)
    elif price <= 650:
        return 65 + (price - 600) * (67.5 - 65) / (650 - 600)
    elif price <= 700:
        return 67.5 + (price - 650) * (70 - 67.5) / (700 - 650)
    elif price <= 750:
        return 70 + (price - 700) * (72.5 - 70) / (750 - 700)
    elif price <= 800:
        return 72.5 + (price - 750) * (75 - 72.5) / (800 - 750)
    elif price <= 850:
        return 75 + (price - 800) * (77.5 - 75) / (850 - 800)
    elif price <= 900:
        return 77.5 + (price - 850) * (80 - 77.5) / (900 - 850)
    elif price <= 950:
        return 80 + (price - 900) * (82.5 - 80) / (950 - 900)
    elif price <= 1000:
        return 82.5 + (price - 950) * (85 - 82.5) / (1000 - 950)
    else: # price > 1000
        return 90