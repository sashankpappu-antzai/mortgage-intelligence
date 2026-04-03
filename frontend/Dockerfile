FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install dependencies
RUN npm install

# Copy frontend source
COPY frontend/ ./

EXPOSE 3000

CMD ["npm", "run", "dev"]
