module.exports = {
  apps: [
    {
      name: "talkeasy-daphne",
      script: "/home/ubuntu/talk_easy/venv/bin/daphne",
      args: "-b 127.0.0.1 -p 8001 talkeasy.asgi:application",
      cwd: "/home/ubuntu/talk_easy",
      interpreter: "none",
      env: {
        DJANGO_SETTINGS_MODULE: "talkeasy.settings",
        DEBUG: "False",
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};

