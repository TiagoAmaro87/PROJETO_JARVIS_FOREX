import random
import numpy as np

# Data from Holy Grail Audit
returns = [0.03] * 139 + [-0.01] * 394 # 26.1% Win Rate at 1:3 RR
iterations = 2000
initial = 1000.0

finals = []
for _ in range(iterations):
    b = initial
    sim = random.choices(returns, k=len(returns))
    for r in sim: b *= (1 + r)
    finals.append(b)

print(f"JARVIS HOLY GRAIL - PROBABILITY REPORT")
print(f"Initial: $1,000 | Trades: 533")
print(f"Probability of Profit: {len([b for b in finals if b > initial])/iterations*100:.1f}%")
print(f"Average Final Balance: ${np.mean(finals):,.2f}")
print(f"Worst Case (2k runs): ${np.min(finals):,.2f}")
print(f"Best Case (2k runs):  ${np.max(finals):,.2f}")
