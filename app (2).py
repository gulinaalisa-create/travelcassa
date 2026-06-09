from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "travelcassa_secret_2024"

# ── Курсы валют к RUB ──────────────────────────────────────────
RATES = {
    "RUB": 1.0,
    "EUR": 100.0,
    "USD": 92.0,
    "GBP": 116.0,
    "TRY": 2.8,
    "THB": 2.5,
}

SYMBOLS = {
    "EUR": "€",
    "RUB": "₽",
    "USD": "$",
    "GBP": "£",
    "TRY": "₺",
    "THB": "฿",
}


# ── Вспомогательные функции ────────────────────────────────────

def get_data():
    """Достаём данные из сессии (или создаём пустые)."""
    if "participants" not in session:
        session["participants"] = []
    if "expenses" not in session:
        session["expenses"] = []
    return session["participants"], session["expenses"]


def convert_to_rub(amount: float, currency: str) -> float:
    """Конвертируем любую валюту в RUB по фиксированному курсу."""
    return round(amount * RATES[currency], 2)


def calculate_balances(participants: list, expenses: list) -> dict:
    """
    Считаем баланс каждого участника.
    paid[X]  — сколько X реально заплатил (в RUB)
    owed[X]  — сколько X должен был по всем тратам
    balance  — paid − owed (>0: ему должны, <0: он должен)
    """
    paid = {p: 0.0 for p in participants}
    owed = {p: 0.0 for p in participants}

    for expense in expenses:
        payer = expense["payer"]
        amount_rub = expense["amount_rub"]
        split = expense["split_between"]

        paid[payer] = round(paid[payer] + amount_rub, 2)

        share = round(amount_rub / len(split), 2)
        for person in split:
            owed[person] = round(owed[person] + share, 2)

    balance = {p: round(paid[p] - owed[p], 2) for p in participants}
    return paid, owed, balance


def settle_debts(balance: dict) -> list:
    """
    Жадный алгоритм минимизации переводов.
    Кредиторы (balance > 0) получают деньги от должников (balance < 0).
    На каждом шаге: самый большой должник платит самому большому кредитору.
    """
    creditors = sorted(
        [(name, amt) for name, amt in balance.items() if amt > 0.01],
        key=lambda x: -x[1]
    )
    debtors = sorted(
        [(name, -amt) for name, amt in balance.items() if amt < -0.01],
        key=lambda x: -x[1]
    )

    # Превращаем в изменяемые списки
    creditors = [list(x) for x in creditors]
    debtors = [list(x) for x in debtors]

    transactions = []
    i, j = 0, 0

    while i < len(creditors) and j < len(debtors):
        transfer = min(creditors[i][1], debtors[j][1])
        transfer = round(transfer, 2)

        transactions.append({
            "from_person": debtors[j][0],
            "to_person": creditors[i][0],
            "amount": transfer,
        })

        creditors[i][1] = round(creditors[i][1] - transfer, 2)
        debtors[j][1] = round(debtors[j][1] - transfer, 2)

        if creditors[i][1] < 0.01:
            i += 1
        if debtors[j][1] < 0.01:
            j += 1

    return transactions


# ── Маршруты (routes) ──────────────────────────────────────────

@app.route("/")
def index():
    """Главная страница — показывает все данные."""
    participants, expenses = get_data()

    # Считаем итоги только если есть данные
    summary = None
    if participants and expenses:
        paid, owed, balance = calculate_balances(participants, expenses)
        debts = settle_debts(balance)
        total = round(sum(e["amount_rub"] for e in expenses), 2)

        summary = {
            "total": total,
            "count": len(expenses),
            "paid": paid,
            "owed": owed,
            "balance": balance,
            "debts": debts,
        }

    return render_template(
        "index.html",
        participants=participants,
        expenses=expenses,
        summary=summary,
        currencies=list(RATES.keys()),
        symbols=SYMBOLS,
    )


@app.route("/add_participant", methods=["POST"])
def add_participant():
    """Добавляем нового участника."""
    participants, _ = get_data()
    name = request.form.get("name", "").strip()

    if name and name not in participants:
        participants.append(name)
        session.modified = True

    return redirect(url_for("index"))


@app.route("/remove_participant/<name>")
def remove_participant(name):
    """Удаляем участника."""
    participants, expenses = get_data()

    if name in participants:
        participants.remove(name)
        # Удаляем все траты этого участника
        session["expenses"] = [
            e for e in expenses
            if e["payer"] != name and name not in e["split_between"]
        ]
        session.modified = True

    return redirect(url_for("index"))


@app.route("/add_expense", methods=["POST"])
def add_expense():
    """Добавляем новую трату."""
    participants, expenses = get_data()

    desc = request.form.get("desc", "").strip()
    payer = request.form.get("payer", "")
    amount_str = request.form.get("amount", "0")
    currency = request.form.get("currency", "EUR")
    split_between = request.form.getlist("split_between")  # список чекбоксов

    # Проверки
    if not desc or not payer or not split_between:
        return redirect(url_for("index"))

    try:
        amount = float(amount_str)
    except ValueError:
        return redirect(url_for("index"))

    if amount <= 0:
        return redirect(url_for("index"))

    amount_rub = convert_to_rub(amount, currency)

    expenses.append({
        "id": len(expenses),
        "desc": desc,
        "payer": payer,
        "amount": amount,
        "amount_rub": amount_rub,
        "currency": currency,
        "symbol": SYMBOLS[currency],
        "split_between": split_between,
    })
    session.modified = True

    return redirect(url_for("index"))


@app.route("/remove_expense/<int:expense_id>")
def remove_expense(expense_id):
    """Удаляем трату по индексу."""
    _, expenses = get_data()
    session["expenses"] = [e for e in expenses if e["id"] != expense_id]
    session.modified = True
    return redirect(url_for("index"))


@app.route("/reset")
def reset():
    """Сбрасываем все данные."""
    session.clear()
    return redirect(url_for("index"))


# ── Запуск ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
