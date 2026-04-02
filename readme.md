## Anaconda (Miniconda)

### First Time Setup
```bash
# Create environment from configuration file
conda env create -f environment.yaml

# Verify environment was created
conda env list

# Verify installed packages
conda list
```

### Updating environment (to match config file)
```bash
# Update environment with any changes to environment.yaml
conda env update -f environment.yaml

# Update and remove packages not in the file (clean)
conda env update -f environment.yaml --prune
```

### Usage
```bash
# Activate environment
conda activate wordome_env

# Deactivate environment
conda deactivate

# Remove environment completely (if)
conda env remove -n wordome_env
```