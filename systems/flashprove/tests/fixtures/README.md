`info.json` and `inputs.json` are what the built image returned (`entrypoint info`, and
`/opt/iproofs/inputs.json`) for a build of `systems/flashprove/Dockerfile` at adapter commit
`a03797986cd880e5d54508e200194768f105f8fc` on 2026-11-05, in a docker VM (16 CPUs, 1,100 s), read
inside that image on a hosted H100 container. The build was from a clean tree, so `adapter_dirty`
is false.