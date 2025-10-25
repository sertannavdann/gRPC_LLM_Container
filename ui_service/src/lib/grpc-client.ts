import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import path from 'path';

// Declare process global for TypeScript
declare const process: {
  env: { [key: string]: string | undefined };
  cwd: () => string;
};

// Get agent address from environment
// In Next.js, this needs to be read at runtime, not build time
// IMPORTANT: Use bracket notation to prevent webpack from replacing at build time
function getAgentAddress(): string {
  // Use bracket notation to avoid webpack DefinePlugin optimization
  const envVarName = 'AGENT_SERVICE_ADDRESS';
  const agentAddress = process.env[envVarName];
  
  console.log('[gRPC Client] getAgentAddress() called');
  console.log('[gRPC Client] Reading env var:', envVarName);
  console.log('[gRPC Client] Value from process.env[]:', agentAddress);
  
  // Return the environment variable or fallback
  if (agentAddress) {
    console.log('[gRPC Client] ✅ Using env var:', agentAddress);
    return agentAddress;
  }
  
  // Fallback to localhost for development
  console.log('[gRPC Client] ⚠️ Using fallback: localhost:50054');
  return 'localhost:50054';
}

// Handle both development and production paths
const PROTO_PATH = path.join(process.cwd(), 'proto', 'agent.proto');

console.log('[gRPC Client] Loading proto from:', PROTO_PATH);

// Load protobuf
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const protoDescriptor = grpc.loadPackageDefinition(packageDefinition) as any;

// The proto has 'package agent;' so the service is under agent.AgentService
const AgentService = protoDescriptor.agent?.AgentService;

if (!AgentService) {
  console.error('[gRPC Client] Failed to load AgentService from proto');
  console.error('[gRPC Client] Available packages:', Object.keys(protoDescriptor));
  throw new Error('AgentService not found in proto definition');
}

let client: any = null;

// Get agent client (create new instance each time to ensure fresh env vars)
function getAgentClient(): any {
  // Use the helper function to get the address
  const agentAddress = getAgentAddress();
  
  console.log('[gRPC Client] Creating new gRPC client');
  console.log('[gRPC Client] Final agent service address:', agentAddress);
  
  const AgentService = protoDescriptor.agent.AgentService;
  return new AgentService(
    agentAddress,
    grpc.credentials.createInsecure()
  );
}

export interface AgentRequest {
  user_query: string;
  debug_mode: boolean;
}

export interface AgentResponse {
  final_answer: string;
  context_used?: string;
  sources?: string;
  execution_graph?: string;
}

export function executeAgent(message: string, threadId?: string): Promise<AgentResponse> {
  return new Promise((resolve, reject) => {
    const client = getAgentClient();
    const metadata = new grpc.Metadata();
    if (threadId) {
      metadata.add('thread-id', threadId);
    }
    
    const request: AgentRequest = {
      user_query: message,
      debug_mode: false,
    };
    
    console.log('[gRPC Client] Executing agent request:', message);
    
    // The proto method is QueryAgent, not ExecuteAgent
    client.QueryAgent(request, metadata, (error: grpc.ServiceError | null, response: AgentResponse) => {
      if (error) {
        console.error('[gRPC Client] Error:', error);
        reject(error);
      } else {
        console.log('[gRPC Client] Success, received response');
        resolve(response);
      }
    });
  });
}
