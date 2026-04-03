## Anaconda (Miniconda)

### First Time Setup
```
# Create environment from configuration file
> conda env create -f environment.yaml

# Verify environment was created
> conda env list
```

### Updating environment (to match config file)
```
# Update environment with any changes to environment.yaml
> conda env update -f environment.yaml

# Update and remove packages not in the file (clean)
> conda env update -f environment.yaml --prune
```

### Usage
```
# Activate environment
> conda activate wordome_env

# Deactivate environment
> conda deactivate
```

## Wordome Application

### Install (Development Mode) 
```
# Install the package in development mode
> pip install -e .

# Conversely, this uninstall command can be useful for troubleshooting
> pip uninstall wordome -y
```

### Running the app
```
# API service
# Note: this alias is defined in within pyproject.toml
> wordome

# Demo mode (executes a fixed flow that showcases basic functionality)
> wordome --mode demo
```

## Utility

### Ruff (code quality tool)
```
# Run this as code changes are made to auto-format and lint code
# Note: fails if corrections cannot be applied automatically
> make ruff
```

## Other Notes

### VS Code - Suggested configs
```
# settings.json
{
    "python-envs.defaultEnvManager": "ms-python.python:conda",
    "python-envs.defaultPackageManager": "ms-python.python:conda",
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        "**/.ruff_cache": true
    },
    "files.autoSave": "onFocusChange"
}
```