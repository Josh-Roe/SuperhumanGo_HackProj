import * as sdk from "@codahq/packs-sdk";
import { mcpEndpoint, networkDomain } from "./config";
import { registerDraftActions } from "./draft-actions";

export const pack = sdk.newPack();
pack.addMCPServer({ name: "HackathonWorkspace", endpointUrl: mcpEndpoint });
pack.addNetworkDomain(networkDomain);
pack.setUserAuthentication({ type: sdk.AuthenticationType.HeaderBearerToken });

registerDraftActions(pack, mcpEndpoint);
