import numpy as np
import torch
import torch.nn as tnn
import torch.nn.functional as F
import torch.optim as topti
from torchtext import data
from torchtext.vocab import GloVe
from imdb_dataloader import IMDB
import re
from string import punctuation


# Class for creating the neural network.
class Network(tnn.Module):
    def __init__(self):
        super(Network, self).__init__()
        self.lstm = tnn.LSTM(50,100,3,batch_first=True, bidirectional=True)
        self.fc1 = tnn.Linear(200, 64)
        self.fc2 = tnn.Linear(64, 1)
        self.dropout = tnn.Dropout(0.7)

    def forward(self, input, length):
        x=tnn.utils.rnn.pack_padded_sequence(input=input,lengths=length,batch_first=True)
        x,(hn,cn)=self.lstm(x)
        output, output_lengths = tnn.utils.rnn.pad_packed_sequence(x)
        hidden = self.dropout(torch.cat((hn[-2,:,:], hn[-1,:,:]), dim = 1))#torch.sum(hn, dim=0))
        x=tnn.functional.relu(self.fc1(hidden))
        x=self.fc2(x)
        x = x.view(-1)
        return x


class PreProcessing():
    def pre(x):
        stop_words = ["the", "a", "and","i","an","are","at","for","in","is",'it',"of","on","to","was","with"] 
        x = [cleanText(c) for c in x if c and c not in set(punctuation)|set(stop_words)] 
        y=[]
        for a in x:
            y += a.split()
        return y

    def post(batch, vocab):
        """Called after numericalization but prior to vectorization"""
        return batch

    text_field = data.Field(lower=True, include_lengths=True, batch_first=True, preprocessing=pre, postprocessing=post)

def cleanText(x):
        x=re.sub(r'[^A-Za-z]+', ' ',x)
        x=re.sub(r'https?:/\/\S+', ' ',x)
        return x.strip()

def lossFunc():
    return tnn.BCEWithLogitsLoss()


def main():
    # Use a GPU if available, as it should be faster.
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("Using device: " + str(device))

    # Load the training dataset, and create a data loader to generate a batch.
    textField = PreProcessing.text_field
    labelField = data.Field(sequential=False)

    train, dev = IMDB.splits(textField, labelField, train="train", validation="dev")

    textField.build_vocab(train, dev, vectors=GloVe(name="6B", dim=50))
    labelField.build_vocab(train, dev)

    trainLoader, testLoader = data.BucketIterator.splits((train, dev), shuffle=True, batch_size=64,
                                                         sort_key=lambda x: len(x.text), sort_within_batch=True)

    net = Network().to(device)
    criterion =lossFunc()
    optimiser = topti.Adam(net.parameters(), lr=0.001)  # Minimise the loss using the Adam algorithm.

    for epoch in range(15):
        running_loss = 0

        for i, batch in enumerate(trainLoader):
            # Get a batch and potentially send it to GPU memory.
            inputs, length, labels = textField.vocab.vectors[batch.text[0]].to(device), batch.text[1].to(
                device), batch.label.type(torch.FloatTensor).to(device)

            labels -= 1

            # PyTorch calculates gradients by accumulating contributions to them (useful for
            # RNNs).  Hence we must manually set them to zero before calculating them.
            optimiser.zero_grad()

            # Forward pass through the network.
            output = net(inputs, length)

            loss = criterion(output, labels)

            loss.backward()

            # Minimise the loss according to the gradient.
            optimiser.step()

            running_loss += loss.item()

            if i % 32 == 31:
                print("Epoch: %2d, Batch: %4d, Loss: %.3f" % (epoch + 1, i + 1, running_loss / 32))
                running_loss = 0

    num_correct = 0

    # Save mode
    torch.save(net.state_dict(), "./model.pth")
    print("Saved model")

    # Evaluate network on the test dataset.  We aren't calculating gradients, so disable autograd to speed up
    # computations and reduce memory usage.
    with torch.no_grad():
        for batch in testLoader:
            # Get a batch and potentially send it to GPU memory.
            inputs, length, labels = textField.vocab.vectors[batch.text[0]].to(device), batch.text[1].to(
                device), batch.label.type(torch.FloatTensor).to(device)

            labels -= 1

            # Get predictions
            outputs = torch.sigmoid(net(inputs, length))
            predicted = torch.round(outputs)

            num_correct += torch.sum(labels == predicted).item()

    accuracy = 100 * num_correct / len(dev)

    print(f"Classification accuracy: {accuracy}")

if __name__ == '__main__':
    main()
