def calculate_groww_intraday(bp, sp, qty, position="LONG"):
    """
    Groww intraday charges + net profit calculation.

    Parameters:
        bp (float): Buy price
        sp (float): Sell price
        qty (int): Quantity
        position (str): "LONG" or "SHORT"

    Returns:
        dict: charges + net profit
    """

    B = bp * qty
    S = sp * qty
    turnover = B + S

    # Brokerage
    brokerage_buy = min(max(0.001 * B, 5), 20)
    brokerage_sell = min(max(0.001 * S, 5), 20)
    brokerage = brokerage_buy + brokerage_sell

    # Charges
    stt = 0.00025 * S
    txn = 0.0000297 * turnover
    gst = 0.18 * (brokerage + txn)
    sebi = 0.000001 * turnover
    stamp = 0.00003 * B

    total_charges = brokerage + stt + txn + gst + sebi + stamp

    # Profit Calculation
    position = position.upper()

    if position == "LONG":
        gross_profit = S - B
    elif position == "SHORT":
        gross_profit = B - S
    else:
        raise ValueError("Position must be 'LONG' or 'SHORT'")

    net_profit = gross_profit - total_charges

    return {
        "Position": position,
        "Quantity": qty,
        "Buy Value": round(bp, 2),
        "Sell Value": round(sp, 2),
        "Gross Profit": round(gross_profit, 2),
        "Total Charges": round(total_charges, 4),
        "Net Profit": round(net_profit, 2)
    }


if __name__ == "__main__":
    result = calculate_groww_intraday(100, 105, 100, position="LONG")
    for k, v in result.items():
        print(f"{k}: ₹{v}")