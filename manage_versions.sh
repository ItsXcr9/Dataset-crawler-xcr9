#!/bin/bash

# Dataset Version Management Script
# Manages dataset versions and tracks what has been trained

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

VERSIONS_DIR="dataset_versions"
REGISTRY_FILE="dataset_registry.json"
TRAINED_LOG="trained_versions.log"

# Initialize registry if it doesn't exist
init_registry() {
    if [ ! -f "$REGISTRY_FILE" ]; then
        cat > "$REGISTRY_FILE" <<EOF
{
  "versions": [],
  "current_version": null,
  "trained_versions": []
}
EOF
        print_success "Initialized dataset registry"
    fi
}

# List all dataset versions
list_versions() {
    init_registry
    
    print_info "============================================"
    print_info "  Dataset Versions"
    print_info "============================================"
    echo ""
    
    if [ ! -f "$REGISTRY_FILE" ]; then
        print_warning "No versions found"
        return
    fi
    
    # Get current version
    CURRENT=$(jq -r '.current_version // "none"' "$REGISTRY_FILE")
    
    # List all versions
    VERSIONS=$(jq -r '.versions[] | @json' "$REGISTRY_FILE" 2>/dev/null || echo "")
    
    if [ -z "$VERSIONS" ]; then
        print_warning "No versions registered"
        echo ""
        print_info "To create a version, run:"
        print_info "  ./manage_versions.sh save <version_name> <description>"
        return
    fi
    
    echo "$VERSIONS" | while IFS= read -r version; do
        NAME=$(echo "$version" | jq -r '.name')
        DATE=$(echo "$version" | jq -r '.created')
        DOCS=$(echo "$version" | jq -r '.stats.total_docs')
        TOKENS=$(echo "$version" | jq -r '.stats.total_tokens')
        DESC=$(echo "$version" | jq -r '.description')
        TRAINED=$(echo "$version" | jq -r '.trained // false')
        
        if [ "$NAME" = "$CURRENT" ]; then
            echo -e "${GREEN}● $NAME${NC} (current)"
        else
            echo -e "${CYAN}○ $NAME${NC}"
        fi
        
        echo "  Created: $DATE"
        echo "  Docs: $DOCS | Tokens: $TOKENS"
        echo "  Description: $DESC"
        
        if [ "$TRAINED" = "true" ]; then
            echo -e "  Status: ${GREEN}✓ Trained${NC}"
        else
            echo -e "  Status: ${YELLOW}○ Not trained${NC}"
        fi
        echo ""
    done
}

# Save current dataset as a version
save_version() {
    VERSION_NAME="$1"
    DESCRIPTION="${2:-No description}"
    
    if [ -z "$VERSION_NAME" ]; then
        print_error "Usage: ./manage_versions.sh save <version_name> [description]"
        exit 1
    fi
    
    init_registry
    
    # Check if version already exists
    EXISTS=$(jq -r ".versions[] | select(.name==\"$VERSION_NAME\") | .name" "$REGISTRY_FILE" 2>/dev/null || echo "")
    if [ -n "$EXISTS" ]; then
        print_error "Version '$VERSION_NAME' already exists!"
        print_info "Use a different name or delete the existing version first"
        exit 1
    fi
    
    # Check if dataset exists
    if [ ! -d "dataset/shards/train" ] || [ -z "$(ls -A dataset/shards/train 2>/dev/null)" ]; then
        print_error "No dataset found in dataset/shards/"
        print_info "Run a crawl first: ./crawl_full_site.sh <url>"
        exit 1
    fi
    
    print_info "Saving dataset version: $VERSION_NAME"
    
    # Create version directory
    VERSION_DIR="$VERSIONS_DIR/$VERSION_NAME"
    mkdir -p "$VERSION_DIR"
    
    # Copy dataset
    print_info "Copying dataset files..."
    cp -r dataset/shards "$VERSION_DIR/"
    cp -r dataset/cleaned "$VERSION_DIR/" 2>/dev/null || true
    cp dataset/VERSION.txt "$VERSION_DIR/" 2>/dev/null || true
    
    # Get statistics
    TRAIN_DOCS=$(jq -r '.total_documents // 0' dataset/shards/train_manifest.json 2>/dev/null || echo "0")
    TRAIN_TOKENS=$(jq -r '.total_tokens // 0' dataset/shards/train_manifest.json 2>/dev/null || echo "0")
    VAL_DOCS=$(jq -r '.total_documents // 0' dataset/shards/val_manifest.json 2>/dev/null || echo "0")
    VAL_TOKENS=$(jq -r '.total_tokens // 0' dataset/shards/val_manifest.json 2>/dev/null || echo "0")
    
    TOTAL_DOCS=$((TRAIN_DOCS + VAL_DOCS))
    TOTAL_TOKENS=$((TRAIN_TOKENS + VAL_TOKENS))
    
    # Update registry
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    jq --arg name "$VERSION_NAME" \
       --arg desc "$DESCRIPTION" \
       --arg date "$TIMESTAMP" \
       --arg docs "$TOTAL_DOCS" \
       --arg tokens "$TOTAL_TOKENS" \
       --arg train_docs "$TRAIN_DOCS" \
       --arg val_docs "$VAL_DOCS" \
       '.versions += [{
         "name": $name,
         "description": $desc,
         "created": $date,
         "stats": {
           "total_docs": ($docs | tonumber),
           "total_tokens": ($tokens | tonumber),
           "train_docs": ($train_docs | tonumber),
           "val_docs": ($val_docs | tonumber)
         },
         "trained": false,
         "path": "'"$VERSION_DIR"'"
       }] | .current_version = $name' "$REGISTRY_FILE" > "${REGISTRY_FILE}.tmp"
    
    mv "${REGISTRY_FILE}.tmp" "$REGISTRY_FILE"
    
    print_success "Version '$VERSION_NAME' saved successfully!"
    print_info "Location: $VERSION_DIR"
    print_info "Documents: $TOTAL_DOCS | Tokens: $TOTAL_TOKENS"
}

# Load a specific version
load_version() {
    VERSION_NAME="$1"
    
    if [ -z "$VERSION_NAME" ]; then
        print_error "Usage: ./manage_versions.sh load <version_name>"
        exit 1
    fi
    
    init_registry
    
    # Check if version exists
    VERSION_PATH=$(jq -r ".versions[] | select(.name==\"$VERSION_NAME\") | .path" "$REGISTRY_FILE" 2>/dev/null || echo "")
    
    if [ -z "$VERSION_PATH" ]; then
        print_error "Version '$VERSION_NAME' not found"
        print_info "Available versions:"
        list_versions
        exit 1
    fi
    
    print_info "Loading version: $VERSION_NAME"
    
    # Backup current dataset
    if [ -d "dataset/shards" ]; then
        BACKUP_DIR="dataset_backups/before_load_$(date +%Y%m%d_%H%M%S)"
        print_info "Backing up current dataset to: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
        mv dataset/shards "$BACKUP_DIR/" 2>/dev/null || true
        mv dataset/cleaned "$BACKUP_DIR/" 2>/dev/null || true
    fi
    
    # Load version
    print_info "Copying version files..."
    mkdir -p dataset
    cp -r "$VERSION_PATH/shards" dataset/
    cp -r "$VERSION_PATH/cleaned" dataset/ 2>/dev/null || true
    cp "$VERSION_PATH/VERSION.txt" dataset/ 2>/dev/null || true
    
    # Update current version
    jq --arg name "$VERSION_NAME" '.current_version = $name' "$REGISTRY_FILE" > "${REGISTRY_FILE}.tmp"
    mv "${REGISTRY_FILE}.tmp" "$REGISTRY_FILE"
    
    print_success "Loaded version: $VERSION_NAME"
    print_info "Dataset ready at: dataset/shards/"
}

# Mark version as trained
mark_trained() {
    VERSION_NAME="$1"
    
    if [ -z "$VERSION_NAME" ]; then
        # Use current version
        VERSION_NAME=$(jq -r '.current_version // empty' "$REGISTRY_FILE" 2>/dev/null)
        if [ -z "$VERSION_NAME" ]; then
            print_error "No current version set"
            print_info "Usage: ./manage_versions.sh trained <version_name>"
            exit 1
        fi
    fi
    
    init_registry
    
    # Update trained status
    jq --arg name "$VERSION_NAME" \
       '(.versions[] | select(.name==$name) | .trained) = true | 
        .trained_versions += [$name] | 
        .trained_versions |= unique' "$REGISTRY_FILE" > "${REGISTRY_FILE}.tmp"
    
    mv "${REGISTRY_FILE}.tmp" "$REGISTRY_FILE"
    
    # Log training
    echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") - Trained version: $VERSION_NAME" >> "$TRAINED_LOG"
    
    print_success "Marked version '$VERSION_NAME' as trained"
}

# Get only untrained versions (for incremental training)
get_untrained() {
    init_registry
    
    print_info "============================================"
    print_info "  Untrained Dataset Versions"
    print_info "============================================"
    echo ""
    
    UNTRAINED=$(jq -r '.versions[] | select(.trained == false) | @json' "$REGISTRY_FILE" 2>/dev/null || echo "")
    
    if [ -z "$UNTRAINED" ]; then
        print_success "All versions have been trained!"
        return
    fi
    
    echo "$UNTRAINED" | while IFS= read -r version; do
        NAME=$(echo "$version" | jq -r '.name')
        DATE=$(echo "$version" | jq -r '.created')
        DOCS=$(echo "$version" | jq -r '.stats.total_docs')
        TOKENS=$(echo "$version" | jq -r '.stats.total_tokens')
        
        echo -e "${YELLOW}● $NAME${NC}"
        echo "  Created: $DATE"
        echo "  Docs: $DOCS | Tokens: $TOKENS"
        echo ""
    done
    
    print_info "To train a version:"
    print_info "  1. ./manage_versions.sh load <version_name>"
    print_info "  2. Train your model using dataset/shards/"
    print_info "  3. ./manage_versions.sh trained <version_name>"
}

# Compare two versions (show diff)
compare_versions() {
    VERSION1="$1"
    VERSION2="$2"
    
    if [ -z "$VERSION1" ] || [ -z "$VERSION2" ]; then
        print_error "Usage: ./manage_versions.sh compare <version1> <version2>"
        exit 1
    fi
    
    init_registry
    
    STATS1=$(jq -r ".versions[] | select(.name==\"$VERSION1\")" "$REGISTRY_FILE")
    STATS2=$(jq -r ".versions[] | select(.name==\"$VERSION2\")" "$REGISTRY_FILE")
    
    if [ -z "$STATS1" ] || [ -z "$STATS2" ]; then
        print_error "One or both versions not found"
        exit 1
    fi
    
    print_info "============================================"
    print_info "  Comparing Versions"
    print_info "============================================"
    echo ""
    
    DOCS1=$(echo "$STATS1" | jq -r '.stats.total_docs')
    DOCS2=$(echo "$STATS2" | jq -r '.stats.total_docs')
    TOKENS1=$(echo "$STATS1" | jq -r '.stats.total_tokens')
    TOKENS2=$(echo "$STATS2" | jq -r '.stats.total_tokens')
    
    echo "Version: $VERSION1"
    echo "  Documents: $DOCS1"
    echo "  Tokens: $TOKENS1"
    echo ""
    echo "Version: $VERSION2"
    echo "  Documents: $DOCS2"
    echo "  Tokens: $TOKENS2"
    echo ""
    
    DOCS_DIFF=$((DOCS2 - DOCS1))
    TOKENS_DIFF=$((TOKENS2 - TOKENS1))
    
    print_info "Difference:"
    echo "  Documents: ${DOCS_DIFF:+"+"}$DOCS_DIFF"
    echo "  Tokens: ${TOKENS_DIFF:+"+"}$TOKENS_DIFF"
}

# Show help
show_help() {
    cat <<EOF
${BLUE}Dataset Version Management${NC}

${GREEN}Usage:${NC}
  ./manage_versions.sh <command> [options]

${GREEN}Commands:${NC}
  ${CYAN}list${NC}                          List all dataset versions
  ${CYAN}save${NC} <name> [description]    Save current dataset as a version
  ${CYAN}load${NC} <name>                  Load a specific version
  ${CYAN}trained${NC} [name]               Mark version as trained
  ${CYAN}untrained${NC}                    List untrained versions only
  ${CYAN}compare${NC} <v1> <v2>            Compare two versions
  ${CYAN}help${NC}                         Show this help

${GREEN}Examples:${NC}
  # Save current dataset
  ./manage_versions.sh save kubernetes_v1 "Initial Kubernetes docs"
  
  # List all versions
  ./manage_versions.sh list
  
  # Load a specific version for training
  ./manage_versions.sh load kubernetes_v1
  
  # After training, mark as trained
  ./manage_versions.sh trained kubernetes_v1
  
  # Find what needs training
  ./manage_versions.sh untrained
  
  # Compare two versions
  ./manage_versions.sh compare kubernetes_v1 kubernetes_v2

${GREEN}Workflow for Incremental Training:${NC}
  1. Crawl new data: ${CYAN}./crawl_full_site.sh <url> 7 mysite_v2${NC}
  2. Save as version: ${CYAN}./manage_versions.sh save mysite_v2 "Updated docs"${NC}
  3. Load version: ${CYAN}./manage_versions.sh load mysite_v2${NC}
  4. Train your model using ${CYAN}dataset/shards/${NC}
  5. Mark as trained: ${CYAN}./manage_versions.sh trained mysite_v2${NC}

EOF
}

# Main command router
case "${1:-help}" in
    list)
        list_versions
        ;;
    save)
        save_version "$2" "$3"
        ;;
    load)
        load_version "$2"
        ;;
    trained)
        mark_trained "$2"
        ;;
    untrained)
        get_untrained
        ;;
    compare)
        compare_versions "$2" "$3"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

