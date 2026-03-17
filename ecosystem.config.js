module.exports = {
  apps: [{
    name: "scavenger-v2",
    script: "/root/scavenger-v2/venv/bin/python3",
    args: "bot.py",
    cwd: "/root/scavenger-v2",
    interpreter: "none",
    env: {
      PATH: "/root/scavenger-v2/venv/bin:" + process.env.PATH
    },
    watch: false,
    autorestart: true,
    max_restarts: 50,
    restart_delay: 3000,
  }]
};
