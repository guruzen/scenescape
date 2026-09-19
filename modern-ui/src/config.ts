type RuntimeConfig={apiBaseUrl:string;keycloakUrl:string;keycloakRealm:string;keycloakClientId:string;appTitle:string}
const env=(window as unknown as {__SCENESCAPE_CONFIG__?:Partial<RuntimeConfig>}).__SCENESCAPE_CONFIG__??{}
export const runtimeConfig:RuntimeConfig={apiBaseUrl:env.apiBaseUrl??'',keycloakUrl:env.keycloakUrl??'/auth',keycloakRealm:env.keycloakRealm??'scenescape',keycloakClientId:env.keycloakClientId??'scenescape-ui',appTitle:env.appTitle??'SceneScape'}
