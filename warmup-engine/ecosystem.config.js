module.exports = {
  apps: [
    {
      name: 'warmup-engine',
      script: './src/index.js',
      cwd: '/opt/warmup-engine',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'production',
        REDIS_HOST: '127.0.0.1',
        REDIS_PORT: 6379,
      },
    },
    {
      name: 'campaign-sender',
      script: 'python3',
      args: 'campaign_worker.py',
      cwd: '/opt/warmup-engine',
      instances: 1,
      exec_mode: 'fork',
      autorestart: false,
      watch: false,
      env: {
        PYTHONUNBUFFERED: '1',
      },
    },
  ],
};
