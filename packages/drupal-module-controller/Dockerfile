FROM python:3.13-slim-trixie

# Install PHP 7.4 from sury repo
RUN apt-get update && apt-get install -y \
    ca-certificates curl gnupg unzip git \
 && curl -fsSL https://packages.sury.org/php/apt.gpg | gpg --dearmor -o /usr/share/keyrings/php.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/php.gpg] https://packages.sury.org/php/ trixie main" \
    > /etc/apt/sources.list.d/php.list \
 && apt-get update && apt-get install -y \
    php7.4 php7.4-cli php7.4-mysql php7.4-gd php7.4-xml php7.4-mbstring \
 && rm -rf /var/lib/apt/lists/*

# Install Drush 8
RUN curl -L https://github.com/drush-ops/drush/releases/download/8.4.12/drush.phar \
    -o /usr/local/bin/drush \
 && chmod +x /usr/local/bin/drush

# Python deps
COPY . /app
RUN pip install --no-cache-dir /app

CMD ["mmoda-drupal-module-controller", "--host", "0.0.0.0", "--port", "8181"]