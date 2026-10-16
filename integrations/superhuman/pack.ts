import * as sdk from "@codahq/packs-sdk";
import { mcpEndpoint } from "./config";

export const pack = sdk.newPack();
pack.addMCPServer({ name: "HackathonWorkspace", endpointUrl: mcpEndpoint });
pack.addNetworkDomain(new URL(mcpEndpoint).hostname);
pack.setUserAuthentication({ type: sdk.AuthenticationType.HeaderBearerToken });
