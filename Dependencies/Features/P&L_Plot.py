import pandas as pd
import matplotlib.pyplot as plt

'''
    Enter the File path and make sure that only the columns are present !!

'''

# Read Excel file
file_path = r"Stocks_PnL_Report_3698758834_19-04-2026_04-06-2026.xlsx"
df = pd.read_excel(file_path)

# Remove leading/trailing spaces from column names
df.columns = df.columns.str.strip()

# Sort by sell date
df['Sell date'] = pd.to_datetime(df['Sell date'], dayfirst=True)
df = df.sort_values('Sell date')

# Green for profit, Red for loss
colors = ['green' if pnl >= 0 else 'red' for pnl in df['Realised P&L']]

plt.figure(figsize=(14, 7))
bars = plt.bar(
    df['Stock name'],
    df['Realised P&L'],
    color=colors
)

# Draw zero line
plt.axhline(y=0, linestyle='--', linewidth=1)

# Show P&L values on bars
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width()/2,
        height,
        f'{height:.0f}',
        ha='center',
        va='bottom' if height >= 0 else 'top',
        fontsize=8
    )

plt.title('Realised P&L by Stock', fontsize=14)
plt.xlabel('Stock')
plt.ylabel('Profit / Loss (₹)')
plt.xticks(rotation=45, ha='right')
plt.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.show()

df.columns = df.columns.str.strip()

df['Sell date'] = pd.to_datetime(df['Sell date'], dayfirst=True)
df = df.sort_values('Sell date')

# ==========================
# Cumulative P&L Curve
# ==========================

df['Cumulative P&L'] = df['Realised P&L'].cumsum()

plt.figure(figsize=(12, 6))

plt.plot(
    df['Sell date'],
    df['Cumulative P&L'],
    marker='o',
    color='blue',
    linewidth=2,
    label='Cumulative P&L'
)

# Fill green above zero, red below zero
plt.fill_between(
    df['Sell date'],
    df['Cumulative P&L'],
    0,
    where=df['Cumulative P&L'] >= 0,
    alpha=0.3,
    color='green'
)

plt.fill_between(
    df['Sell date'],
    df['Cumulative P&L'],
    0,
    where=df['Cumulative P&L'] < 0,
    alpha=0.3,
    color='red'
)

plt.axhline(0, color='black', linestyle='--')

plt.title('Cumulative P&L Curve')
plt.xlabel('Date')
plt.ylabel('Cumulative Profit (₹)')
plt.grid(True, alpha=0.3)
plt.legend()

plt.tight_layout()
plt.show()

# ==========================
# Daily P&L Bar Chart
# ==========================

daily_pnl = (
    df.groupby('Sell date')['Realised P&L']
      .sum()
      .reset_index()
)

colors = [
    'green' if pnl >= 0 else 'red'
    for pnl in daily_pnl['Realised P&L']
]

plt.figure(figsize=(12, 6))

bars = plt.bar(
    daily_pnl['Sell date'],
    daily_pnl['Realised P&L'],
    color=colors
)

plt.axhline(0, color='black', linestyle='--')

# Show values on bars
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width()/2,
        height,
        f'{height:.0f}',
        ha='center',
        va='bottom' if height >= 0 else 'top',
        fontsize=8
    )

net_pnl = df['Realised P&L'].sum()
# ==========================
# Trading Statistics
# ==========================

net_pnl = df['Realised P&L'].sum()

total_trades = len(df)

winning_trades = (df['Realised P&L'] > 0).sum()
losing_trades = (df['Realised P&L'] < 0).sum()

accuracy = (
    winning_trades / total_trades * 100
    if total_trades > 0 else 0
)

total_buy_value = 18000

profit_pct = (
    net_pnl / total_buy_value * 100
    if total_buy_value > 0 else 0
)

print("\n===== Trading Statistics =====")
print(f"Total Trades    : {total_trades}")
print(f"Winning Trades  : {winning_trades}")
print(f"Losing Trades   : {losing_trades}")
print(f"Accuracy        : {accuracy:.2f}%")
print(f"Net Profit      : ₹{net_pnl:,.2f}")
print(f"Capital Deployed: ₹{total_buy_value:,.2f}")
print(f"Profit %        : {profit_pct:.2f}%")
print(f"\nNet P&L = ₹{net_pnl:,.2f}")

plt.title(
    f'Realised P&L by Stock\nNet P&L: ₹{net_pnl:,.2f}',
    fontsize=14
)
plt.xlabel('Date')
plt.ylabel('Profit / Loss (₹)')
plt.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.show()