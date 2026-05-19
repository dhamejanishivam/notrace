# NoTrace Chat

**Live at:** [chat.shivamdhamejani.in](https://chat.shivamdhamejani.in)

NoTrace is a zero-knowledge, browser-based, purely ephemeral E2EE (End-to-End Encrypted) chat application. It is designed with a paranoid architecture where the server acts strictly as a blind relay and holds zero metadata about its users.

## Security & Privacy Architecture

* **True End-to-End Encryption:** Uses the native Web Crypto API (`RSA-OAEP` 2048-bit). Keys are generated in the browser and the private key *never* leaves the client's local storage.
* **Zero-Knowledge Server:** The backend only sees Base64 ciphertext. It cannot read messages, nor does it want to.
* **No IP Logging:** Werkzeug and Engine.IO logging are strictly suppressed. The server does not log or track connection IPs.
* **Ephemeral By Design:**
  * "Burn" messages dissolve locally after being read based on word-count timers.
  * Offline queues (for undelivered messages) are purged the millisecond the recipient fetches them.
* **No PII Required:** No emails, phone numbers, or passwords. Identities are pseudonymous IDs tied to a cryptographic hash.

## Tech Stack

* **Frontend:** Vanilla JavaScript, HTML5, CSS3, Web Crypto API
* **Backend:** Python, Flask, Flask-SocketIO
* **Database:** SQLite (strictly used as a temporary offline message queue and public-key distributor)

## Local Development Setup

Want to audit the code or run your own instance? It's incredibly lightweight.

### Prerequisites

* Python 3.8+
* Node.js (Optional, if you want to use a specific process manager, but native Python works fine)

### Installation

1. **Clone the repository:**

```bash
git clone https://github.com/dhamejanishivam/notrace.git
cd notrace
```

2. **Set up a virtual environment (Recommended):**

```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies:**

```bash
pip install flask flask-socketio python-dotenv
```

4. **Set your environment variables:**

Create a `.env` file in the root directory:

```env
ADMIN_SECRET_KEY=your_super_secret_password_here
```

5. **Run the server:**

```bash
python app.py
```

The app will be available at `http://localhost:5004`.

## Contributing & Auditing

This project is source-available because cryptography requires transparency. If you are a developer, pentester, or cryptography enthusiast, I invite you to try and break the implementation, find metadata leaks, or submit PRs to harden the security.

## License & Terms of Use

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** license. 

* **What you can do:** You are free to share, copy, modify, and self-host this project for personal use, auditing, or educational purposes.
* **What you cannot do:** You **cannot** use this material, its source code, or any derivatives for commercial purposes. You are strictly prohibited from selling this software, charging for access to instances of it, or using it as a commercial service.

For the full legal text, please refer to the `LICENSE` file in this repository.
