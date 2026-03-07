@echo off
set PATH=C:\Users\harrison.seaborn\AppData\Local\node\node-v20.11.0-win-x64;%PATH%
cd /d "C:\Users\harrison.seaborn\Documents\trading-strategies\trading-strategies\dashboard"
echo Node version:
node --version
echo npm version:
npm --version
echo.
echo Running npm install...
npm install
echo.
echo Done! Run 'npm run dev' to start the dashboard.
