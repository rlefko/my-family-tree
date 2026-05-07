// Generate src/routeTree.gen.ts from the file-based routes without spinning
// up the dev server. Used by `yarn build` so tsc has the generated module
// before it runs.
import { Generator, getConfig, physicalGetRouteNodes } from "@tanstack/router-generator";
import path from "node:path";

const root = path.resolve(process.cwd());
const config = await getConfig({
  routesDirectory: path.join(root, "src", "routes"),
  generatedRouteTree: path.join(root, "src", "routeTree.gen.ts"),
  quoteStyle: "double",
  semicolons: true,
});

const generator = new Generator({
  config,
  root,
  getRouteNodes: physicalGetRouteNodes,
});
await generator.run();
console.log("routeTree.gen.ts written");
