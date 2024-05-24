import time
import datetime
import torch
import torch.jit
from utils.utils_ import log_string
from model.model_ import *
from utils.utils_ import load_data

def get_free_cuda_device():
    # Check if GPU is available
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        if device_count > 0:
            # Iterate over available devices to find the one with the most free memory
            free_memory = [torch.cuda.memory_reserved(i) - torch.cuda.memory_allocated(i) for i in range(device_count)]
            device_index = free_memory.index(max(free_memory))
            device = torch.device(f'cuda:{device_index}')
            return device
        else:
            return torch.device('cpu')  # No CUDA devices available, use CPU
    else:
        return torch.device('cpu')  # CUDA not available, use CPU

def train(model, args, log, loss_criterion, optimizer, scheduler):

     # Get the free CUDA device
    device = get_free_cuda_device()
    if device.type == 'cuda':
        log_string(log, f'Using CUDA device: {torch.cuda.get_device_name(device)}')
    else:
        log_string(log, 'No CUDA devices available, using CPU for computation')

    # Move model to GPU if available
    model.to(device)
    #print("Model moved to GPU")  # Print statement
    #log_string(log, "Model moved to GPU")  # Logging statement
    loss_criterion.to(device)

    (trainX, trainTE, trainY, valX, valTE, valY, testX, testTE,
     testY, SE, mean, std) = load_data(args)
    # load data
    log_string(log, 'data loaded!...')


    num_train, _, num_vertex = trainX.shape
    log_string(log, '**** training model ****')
     
    num_val = valX.shape[0]
    
    train_num_batch = math.ceil(num_train / args.batch_size)
    val_num_batch = math.ceil(num_val / args.batch_size)


    
    wait = 0
    val_loss_min = float('inf')
    best_model_wts = None
    train_total_loss = []
    val_total_loss = []

    if torch.cuda.is_available():
        trainX = trainX.to(device)
        trainTE = trainTE.to(device)
        trainY = trainY.to(device)
        valX = valX.to(device)
        valTE = valTE.to(device)
        valY = valY.to(device)
        testX = testX.to(device)
        testTE = testTE.to(device)
        testY = testY.to(device)
        SE= SE.to(device)
        mean = mean.to(device)
        std = std.to(device)
        log_string(log, "Data moved to GPU")  # Logging statement

    # Train & validation
    for epoch in range(args.max_epoch):
        if wait >= args.patience:
            log_string(log, f'early stop at epoch: {epoch:04d}')
            break
        # shuffle
        permutation = torch.randperm(num_train)

         
        trainX = trainX[permutation]
        
        trainTE = trainTE[permutation]
        trainY = trainY[permutation]
        # train
        start_train = time.time()
        model.train()
        
        train_loss = 0
        for batch_idx in range(train_num_batch):
            start_idx = batch_idx * args.batch_size
            
            end_idx = min(num_train, (batch_idx + 1) * args.batch_size)
            X = trainX[start_idx: end_idx]
            TE = trainTE[start_idx: end_idx]
            
            label = trainY[start_idx: end_idx]
            
            optimizer.zero_grad()


            X = X.to(device)
            TE = TE.to(device)

            
            pred = model(X, TE)
            print ("checkpoint")
            
            pred = pred * std + mean
            loss_batch = loss_criterion(pred, label)
            train_loss += float(loss_batch) * (end_idx - start_idx)
            loss_batch.backward()
            optimizer.step()
            
            

            if torch.cuda.is_available():
                print ("checkpoint - inside")
                torch.cuda.empty_cache()
            if (batch_idx+1) % 5 == 0:
                print(f'Training batch: {batch_idx+1} in epoch:{epoch}, training batch loss:{loss_batch:.4f}')
            del X, TE, label, pred, loss_batch
        train_loss /= num_train
        train_total_loss.append(train_loss)
        end_train = time.time()

        # val loss
        start_val = time.time()
        val_loss = 0
        model.eval()
        with torch.no_grad():
            for batch_idx in range(val_num_batch):
                start_idx = batch_idx * args.batch_size
                end_idx = min(num_val, (batch_idx + 1) * args.batch_size)
                X = valX[start_idx: end_idx]
                TE = valTE[start_idx: end_idx]
                label = valY[start_idx: end_idx]
                pred = model(X, TE)
                pred = pred * std + mean
                loss_batch = loss_criterion(pred, label)
                val_loss += loss_batch * (end_idx - start_idx)
                del X, TE, label, pred, loss_batch
        val_loss /= num_val
        val_total_loss.append(val_loss)
        end_val = time.time()
        log_string(
            log,
            '%s | epoch: %04d/%d, training time: %.1fs, inference time: %.1fs' %
            (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), epoch + 1,
             args.max_epoch, end_train - start_train, end_val - start_val))
        log_string(
            log, f'train loss: {train_loss:.4f}, val_loss: {val_loss:.4f}')
        if val_loss <= val_loss_min:
            log_string(log,f'val loss decrease from {val_loss_min:.4f} to {val_loss:.4f}, saving model to {args.model_file}')
            wait = 0
            val_loss_min = val_loss
            best_model_wts = model.state_dict()
            torch.save(best_model_wts, 'best_model_weights.pt')
        else:
            wait += 1
        scheduler.step()
	
	
    model.load_state_dict(best_model_wts)
    torch.save(model, args.model_file)
        
    log_string(log, f'Training and validation are completed, and model has been stored as {args.model_file}')	
    return train_total_loss, val_total_loss
        
	
	## using torchscript

    #model_scripted = torch.jit.script(model)  # Convert the trained model to a scripted module
    #model_scripted.save(args.model_file)
   
	


    