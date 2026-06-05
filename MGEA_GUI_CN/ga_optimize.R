suppressMessages({
  library(nnet); library(gbm); library(randomForest); library(genalg)
})

element_names <- c("Li","B","O","F","Na","Mg","Al","Si","P","K","Ca","Ti","Fe","Sr","Zr","Ba","Pb")
valence <- c(1, 3, -2, -1, 1, 2, 3, 4, 5, 1, 2, 4, 3, 2, 4, 2, 2)
data_dir  <- "data/"
model_dir <- "models/"

d1 <- read.csv(file.path(data_dir, "10GHz介电常数.csv"), encoding = "UTF-8")[, -1]
d2 <- read.csv(file.path(data_dir, "1GHz介电损耗.csv"),    encoding = "UTF-8")[, -1]
d3 <- read.csv(file.path(data_dir, "RT热导率.csv"),        encoding = "UTF-8")[, -1]
d4 <- read.csv(file.path(data_dir, "20-300热膨胀系数.csv"), encoding = "UTF-8")[, -1]
d5 <- read.csv(file.path(data_dir, "杨氏模量.csv"),        encoding = "UTF-8")[, -1]
names(d1)[ncol(d1)] <- "permittivity"
names(d2)[ncol(d2)] <- "loss"
names(d3)[ncol(d3)] <- "thermalC"
names(d4)[ncol(d4)] <- "expansion"
names(d5)[ncol(d5)] <- "modulus"

all_models <- vector("list", 5)
load(file.path(model_dir, "ann_permittivity_models.RData")); all_models[[1]] <- models; rm(models)
load(file.path(model_dir, "ann_loss_models.RData"));         all_models[[2]] <- models; rm(models)
load(file.path(model_dir, "ann_thermalC_models.RData"));     all_models[[3]] <- models; rm(models)
load(file.path(model_dir, "gbdt_expansion_models_1.RData")); all_models[[4]] <- models; rm(models)
load(file.path(model_dir, "rf_modulus_models_1.RData"));     all_models[[5]] <- models; rm(models)

prop_keys <- c("permittivity","loss","thermalC","expansion","modulus")
prop_stats <- list(
  permittivity = list(q05=quantile(d1$permittivity, 0.05, na.rm=TRUE),
                      q95=quantile(d1$permittivity, 0.95, na.rm=TRUE)),
  loss = list(q05=quantile(exp(-d2$loss), 0.05, na.rm=TRUE),
              q95=quantile(exp(-d2$loss), 0.95, na.rm=TRUE)),
  thermalC = list(q05=quantile(exp(d3$thermalC/10), 0.05, na.rm=TRUE),
                  q95=quantile(exp(d3$thermalC/10), 0.95, na.rm=TRUE)),
  expansion = list(q05=quantile(d4$expansion, 0.05, na.rm=TRUE),
                   q95=quantile(d4$expansion, 0.95, na.rm=TRUE)),
  modulus = list(q05=quantile(d5$modulus, 0.05, na.rm=TRUE),
                 q95=quantile(d5$modulus, 0.95, na.rm=TRUE))
)

predict_one <- function(input_df, bootstrap_n = 1000L) {
  n <- min(bootstrap_n, 1000L)
  idx <- sample(1000L, n)
  p1 <- vapply(idx, function(i) predict(all_models[[1]][[i]], input_df), numeric(1))
  perm <- mean(p1[p1 != 0]); perm_sd <- sd(p1[p1 != 0])
  p2 <- vapply(idx, function(i) exp(-predict(all_models[[2]][[i]], input_df)), numeric(1))
  loss <- mean(p2[p2 != 0]); loss_sd <- sd(p2[p2 != 0])
  p3 <- vapply(idx, function(i) exp(predict(all_models[[3]][[i]], input_df) / 10), numeric(1))
  tc <- mean(p3[p3 != 0]); tc_sd <- sd(p3[p3 != 0])
  expn <- predict(all_models[[4]][[1]], input_df); expn_sd <- NA
  mod  <- predict(all_models[[5]][[1]], input_df); mod_sd   <- NA
  c(perm, perm_sd, loss, loss_sd, tc, tc_sd, expn, expn_sd, mod, mod_sd)
}

input_from_raw <- function(raw_comp) {
  charge <- raw_comp * valence
  raw_comp[3] <- (sum(charge) - charge[3]) / 2
  s <- sum(raw_comp)
  if (s <= 0) return(NULL)
  input_vec <- raw_comp / s * 100
  input_df <- as.data.frame(matrix(input_vec, nrow = 1))
  names(input_df) <- element_names
  input_df
}

norm_comp_from_raw <- function(raw_comp) {
  charge <- raw_comp * valence
  raw_comp[3] <- (sum(charge) - charge[3]) / 2
  s <- sum(raw_comp)
  if (s <= 0) return(setNames(rep(0, 17), element_names))
  setNames(round(raw_comp / s * 100, 2), element_names)
}

# Read job from command line
args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_file <- args[2]

library(jsonlite)
job <- fromJSON(input_file)

# Extract parameters
popSize <- job$popSize
iters   <- job$iters
mut     <- job$mutationChance
niter   <- job$bootstrap_n
min_ratio <- as.numeric(job$min_ratio)
max_ratio <- as.numeric(job$max_ratio)
dir    <- job$dir
wt_use <- as.numeric(job$wt)
names(dir) <- prop_keys
names(wt_use) <- prop_keys
if (sum(wt_use) <= 0) wt_use <- setNames(rep(0.2, 5), prop_keys)
wt_use <- wt_use / sum(wt_use)

evaluate <- function(x) {
  charge <- x * valence
  x[3] <- (sum(charge) - charge[3]) / 2
  s <- sum(x)
  if (s <= 0) return(1e9)
  input_vec <- x / s * 100
  input_df  <- as.data.frame(matrix(input_vec, nrow = 1))
  names(input_df) <- element_names
  preds <- suppressMessages(predict_one(input_df, bootstrap_n = niter))
  if (anyNA(preds)) return(1e9)
  mean_vals <- setNames(c(preds[1], preds[3], preds[5], preds[7], preds[9]), prop_keys)
  scores <- vapply(prop_keys, function(nm) {
    s <- (mean_vals[[nm]] - prop_stats[[nm]]$q05) / (prop_stats[[nm]]$q95 - prop_stats[[nm]]$q05)
    if (dir[[nm]] == "min") s <- 1 - s
    max(0, min(1, s))
  }, numeric(1))
  -sum(scores * wt_use)
}

set.seed(42)
cat("Running GA: popSize=", popSize, " iters=", iters, "\n", sep="")
cat("stringMin:", min_ratio, "\n")
cat("stringMax:", max_ratio, "\n")

rbga.res <- tryCatch({
  rbga(stringMin = min_ratio, stringMax = max_ratio,
       popSize = popSize, iters = iters, elitism = min(2, floor(popSize/10)),
       evalFunc = evaluate, mutationChance = mut,
       verbose = TRUE)
}, error = function(e) {
  list(error = e$message)
})

if (!is.null(rbga.res$error)) {
  out <- list(error = rbga.res$error)
  write_json(out, output_file, auto_unbox = TRUE)
  quit(status = 0)
}

n_iters <- length(rbga.res$population)
cat("Population object class:", class(rbga.res$population), "\n")

# genalg stores population as a flat matrix (popSize × nGenes) for rbga
if (is.matrix(rbga.res$population)) {
  pop_mat <- rbga.res$population
} else if (is.list(rbga.res$population) && is.matrix(rbga.res$population[[1]])) {
  pop_mat <- do.call(rbind, lapply(seq_len(length(rbga.res$population)), function(i) {
    cbind(rbga.res$population[[i]], generation = i)
  }))
} else {
  out <- list(error = paste("Unknown population format. class:", class(rbga.res$population)))
  write_json(out, output_file, auto_unbox = TRUE)
  quit(status = 0)
}

if (is.matrix(pop_mat) && ncol(pop_mat) == 17) {
  all_pop <- cbind(pop_mat, generation = 1)
} else {
  all_pop <- pop_mat
}
colnames(all_pop) <- c(element_names, "generation")
best_individuals <- unique(all_pop[, element_names, drop = FALSE])
n_best <- min(200, nrow(best_individuals))
best_individuals <- best_individuals[1:n_best, , drop = FALSE]

results <- list()
for (i in seq_len(nrow(best_individuals))) {
  input_df <- input_from_raw(as.numeric(best_individuals[i, ]))
  if (is.null(input_df)) next
  preds <- predict_one(input_df, bootstrap_n = niter)
  nc <- norm_comp_from_raw(as.numeric(best_individuals[i, ]))
  mean_vals <- setNames(c(preds[1], preds[3], preds[5], preds[7], preds[9]), prop_keys)
  row <- c(as.list(nc), setNames(as.list(preds), c(
    "permittivity","permittivity_sd","loss","loss_sd",
    "thermalC","thermalC_sd","expansion","expansion_sd","modulus","modulus_sd")))
  scores <- vapply(prop_keys, function(nm) {
    s <- (mean_vals[[nm]] - prop_stats[[nm]]$q05) / (prop_stats[[nm]]$q95 - prop_stats[[nm]]$q05)
    if (dir[[nm]] == "min") s <- 1 - s
    max(0, min(1, s))
  }, numeric(1))
  row$Composite <- sum(scores * wt_use)
  results[[i]] <- row
}

df <- do.call(rbind, lapply(Filter(Negate(is.null), results), as.data.frame))
df <- df[order(-df$Composite), ]
rownames(df) <- NULL

out <- list(results = as.list(df))
write_json(out, output_file, auto_unbox = TRUE, pretty = FALSE, digits = 10)
cat("Done. Results written to", output_file, "\n")
