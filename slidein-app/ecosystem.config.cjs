/**
 * PM2 process definition for the Slidein client dashboard.
 */
module.exports = {
  apps: [
    {
      name: "slidein-app",
      cwd: "/var/www/slidein-app",
      script: "npm",
      args: "run start",
      instances: 1,
      autorestart: true,
      env: {
        NODE_ENV: "production",
        PORT: 3000,
      },
    },
  ],
};
