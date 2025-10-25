import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import path from 'path';

// Handle both development and production paths
const isDev = process.env.NODE_ENV !== 'production';
const PROTO_PATH = isDev 
  ? path.join(process.cwd(), 'proto', 'agent.proto')
  : path.join(process.cwd(), 'proto', 'agent.proto');

const AGENT_SERVICE_ADDRESS = process.env.AGENT_SERVICE_ADDRESS || 'localhost:50054';

console.log('[gRPC Client] Loading proto from:', PROTO_PATH);
console.log('[gRPC Client] Agent service address:', AGENT_SERVICE_ADDRESS);

// Load protobuf
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const protoDescriptor = grpc.loadPackageDefinition(packageDefinition) as any;

// Access the AgentService from the loaded proto
const AgentService = protoDescriptor.AgentService;

if (!AgentService) {
  console.error('[gRPC Client] Failed to load AgentService from proto');
  throw new Error('AgentService not found in proto definition');
}

let client: any = null;

export function getAgentClient() {
  if (!client) {
    console.log('[gRPC Client] Creating new gRPC client');
    client = new AgentService(
      AGENT_SERVICE_ADDRESS,
      grpc.credentials.createInsecure()
    );
  }
  return client;
}

export interface AgentRequest {
  session_id: string;
  user_input: string;
  enable_streaming: boolean;
}

export interface AgentResponse {
  final_answer: string;
  intermediate_steps?: any[];
}

export function executeAgent(request: AgentRequest): Promise<AgentResponse> {
  return new Promise((resolve, reject) => {
    const client = getAgentClient();
    
    console.log('[gRPC Client] Executing agent request:', request.user_input);
    
    client.ExecuteAgent(request, (error: grpc.ServiceError | null, response: AgentResponse) => {
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
