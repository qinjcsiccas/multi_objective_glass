suppressMessages({
  library(nnet); library(gbm); library(randomForest)
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
  permittivity = list(q05=quantile(d1$permittivity,0.05,na.rm=TRUE),
                      q95=quantile(d1$permittivity,0.95,na.rm=TRUE)),
  loss = list(q05=quantile(exp(-d2$loss),0.05,na.rm=TRUE),
              q95=quantile(exp(-d2$loss),0.95,na.rm=TRUE)),
  thermalC = list(q05=quantile(exp(d3$thermalC/10),0.05,na.rm=TRUE),
                  q95=quantile(exp(d3$thermalC/10),0.95,na.rm=TRUE)),
  expansion = list(q05=quantile(d4$expansion,0.05,na.rm=TRUE),
                   q95=quantile(d4$expansion,0.95,na.rm=TRUE)),
  modulus = list(q05=quantile(d5$modulus,0.05,na.rm=TRUE),
                 q95=quantile(d5$modulus,0.95,na.rm=TRUE))
)

predict_one <- function(input_df, bootstrap_n = 1000L) {
  n <- min(bootstrap_n, 1000L)
  idx <- sample(1000L, n)
  p1 <- vapply(idx, function(i) predict(all_models[[1]][[i]], input_df), numeric(1))
  perm_mean <- mean(p1[p1 != 0])
  perm_sd   <- sd(p1[p1 != 0])
  p2 <- vapply(idx, function(i) exp(-predict(all_models[[2]][[i]], input_df)), numeric(1))
  loss_mean <- mean(p2[p2 != 0])
  loss_sd   <- sd(p2[p2 != 0])
  p3 <- vapply(idx, function(i) exp(predict(all_models[[3]][[i]], input_df) / 10), numeric(1))
  tc_mean <- mean(p3[p3 != 0])
  tc_sd   <- sd(p3[p3 != 0])
  expn_mean <- predict(all_models[[4]][[1]], input_df)
  expn_sd   <- NA
  mod_mean  <- predict(all_models[[5]][[1]], input_df)
  mod_sd    <- NA
  c(perm_mean, perm_sd, loss_mean, loss_sd, tc_mean, tc_sd, expn_mean, expn_sd, mod_mean, mod_sd)
}

prop_mean_sd_keys <- c("permittivity","permittivity_sd","loss","loss_sd",
                       "thermalC","thermalC_sd","expansion","expansion_sd","modulus","modulus_sd")

# outputs named list from prediction vector
pred_to_list <- function(preds) {
  setNames(as.list(preds), prop_mean_sd_keys)
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

# ====== Persistent server mode ======
args <- commandArgs(trailingOnly = TRUE)
mode <- if (length(args) > 0) args[1] else "server"

if (mode == "once") {
  # --- One-shot prediction from CSV input file ---
  input_csv <- args[2]
  output_json <- args[3]
  bootstrap_n <- if (length(args) > 3) as.integer(args[4]) else 1000L
  
  raw_data <- read.csv(input_csv)
  results <- list()
  for (r in seq_len(nrow(raw_data))) {
    rc <- as.numeric(raw_data[r, 1:17])
    names(rc) <- element_names
    idf <- input_from_raw(rc)
    if (is.null(idf)) { results[[r]] <- rep(NA,10); next }
    preds <- predict_one(idf, bootstrap_n)
    nc <- norm_comp_from_raw(rc)
    results[[r]] <- c(as.list(nc), pred_to_list(preds))
  }
  df <- do.call(rbind, lapply(results, as.data.frame))
  library(jsonlite)
  write_json(df, output_json, auto_unbox=TRUE, digits = 10)
  
} else {
  # --- Persistent server: watch directory for job files ---
  job_dir <- if (length(args) > 1) args[2] else "job_queue"
  dir.create(job_dir, showWarnings = FALSE)
  cat("Server ready. Watching", job_dir, "\n")
  
  while (TRUE) {
    jobs <- list.files(job_dir, pattern = "request_.*\\.json$", full.names = TRUE)
    for (job_file in jobs) {
      job_id <- gsub("request_|\\.json$", "", basename(job_file))
      out_file <- file.path(job_dir, paste0("response_", job_id, ".json"))
      if (file.exists(out_file)) next  # already processed
      
      library(jsonlite)
      job <- fromJSON(job_file)
      raw_data <- as.data.frame(job$composition)
      names(raw_data) <- element_names
      bootstrap_n <- if (is.null(job$bootstrap_n)) 1000L else job$bootstrap_n
      
      idf <- input_from_raw(as.numeric(raw_data))
      if (is.null(idf)) {
        write_json(list(error = "Invalid composition"), out_file)
      } else {
        preds <- predict_one(idf, bootstrap_n)
        nc <- norm_comp_from_raw(as.numeric(raw_data))
        out <- c(as.list(nc), pred_to_list(preds),
                 list(`_model_input` = setNames(round(as.numeric(idf), 6), element_names)))
        write_json(out, out_file, auto_unbox = TRUE, digits = 10)
      }
      file.remove(job_file)
    }
    Sys.sleep(0.5)
  }
}
