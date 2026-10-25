# Boiler_Return

## Run locally and on another device

1. Install the backend dependencies with `python3 -m pip install -r backend/requirements.txt`.
2. Set `GEMINI_API_KEY` in the environment or in `backend/Gemini API/.env`.
3. Start Flask from the repository root with `python3 backend/app.py`.
4. In another terminal, start the frontend with `cd frontend && npm install && npm run dev`.
5. Find this computer's local network IP. On macOS Wi-Fi, run `ipconfig getifaddr en0`.
6. On a phone or other computer connected to the same trusted Wi-Fi network, open `http://<that-IP>:5173` (for example, `http://192.168.1.25:5173`).

Keep both terminal processes running while using the site. The frontend proxies
API calls to Flask, so the other device does not need to access `localhost:5001`
directly. If macOS asks, allow incoming connections for the development server.
Do not expose these development servers to the public internet or configure
router port forwarding; the app is intended for a trusted local network.

Found-item reports require a photo. Flask uses Gemini to create a public-safe
listing description and private recovery quiz, then stores the item, quiz
evidence, and image in `backend/Database/data.csv` and `backend/Database/Images`.
The quiz question and grading outcome are served through the backend; private
grading evidence is not returned to the frontend.