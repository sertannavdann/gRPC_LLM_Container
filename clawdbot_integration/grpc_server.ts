// clawdbot_integration/grpc_server.ts
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import * as path from 'path';

// Adjust path as needed based on container layout
const PROTO_PATH = path.join(__dirname, '../shared/proto/clawdbot.proto');

// Mock load option since we don't have the file structure fully synced yet
// This requires the proto file to exist.
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true
});

const clawdbotProto = grpc.loadPackageDefinition(packageDefinition).clawdbot as any;

// Placeholder for bot instance
const bot = {
  sendMessage: (userId: string, message: string) => {
    console.log(`[MOCK TELEGRAM] Sending to ${userId}: ${message}`);
  }
};

// Placeholder for websocket server
const wsServer = {
  sendToClient: (userId: string, payload: any) => {
    console.log(`[MOCK UI] Sending to ${userId}:`, payload);
  }
};

// Placeholder for context cache
const contextCache = new Map<string, any>();

// Helper to determine user channel preference
function getUserChannel(userId: string): 'telegram' | 'ui' {
  // Logic to look up user preference
  return 'telegram';
}

// Implement ClawdbotService
function sendMessage(call: any, callback: any) {
  const { user_id, message, context } = call.request;
  
  // Route to Telegram or local UI based on user preferences
  const channel = getUserChannel(user_id);  // telegram | ui
  
  if (channel === 'telegram') {
    // Send via Telegram Bot API
    bot.sendMessage(user_id, message);
  } else {
    // Send via WebSocket to local UI
    wsServer.sendToClient(user_id, { message, context });
  }
  
  callback(null, { success: true, message_id: Date.now().toString() });
}

function getContextSnapshot(call: any, callback: any) {
  const { user_id } = call.request;
  
  // Fetch latest dashboard context (cached in memory)
  const context = contextCache.get(user_id) || {};
  
  callback(null, { context: JSON.stringify(context) });
}

// Start gRPC server
function startServer() {
    const server = new grpc.Server();
    server.addService(clawdbotProto.ClawdbotService.service, {
      sendMessage,
      getContextSnapshot
    });
    
    server.bindAsync(
      '0.0.0.0:50060',
      grpc.ServerCredentials.createInsecure(),
      (err, port) => {
        if (err) {
            console.error(err);
            return;
        }
        console.log(`Clawdbot gRPC server listening on :${port}`);
        server.start();
      }
    );
}

if (require.main === module) {
    startServer();
}
